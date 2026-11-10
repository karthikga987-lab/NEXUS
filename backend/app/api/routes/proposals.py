
import logging
import os
import re

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company, Proposal, SourceDocument
from app.models.entities import (
    ProposalAnalysis,
    AnalysisEvidence,
    Feedback,
    feedback_topics,
)
from app.schemas.contracts import ProposalAnalyzeIn

from app.intelligence.embeddings import (
    EmbeddingError,
    search_similar_chunks,
    search_external_public_chunks,
)
from app.intelligence.proposal_analysis import (
    ProposalAnalysisError,
    analyze_proposal_with_evidence,
)

from app.knowledge_graph.builder import build_company_graph
from app.knowledge_graph.traversal import (
    get_company_events,
    get_event_relationships,
)


logger = logging.getLogger(__name__)

PROPOSAL_INTERNAL_MIN_SIMILARITY = float(
    os.getenv("NEXUS_PROPOSAL_INTERNAL_MIN_SIMILARITY", "0.70")
)

if not -1.0 <= PROPOSAL_INTERNAL_MIN_SIMILARITY <= 1.0:
    raise ValueError(
        "NEXUS_PROPOSAL_INTERNAL_MIN_SIMILARITY "
        "must be between -1.0 and 1.0."
    )


router = APIRouter()

MAX_CUSTOMER_FEEDBACK = 30

# Common words are excluded from simple keyword-based feedback matching.
FEEDBACK_STOPWORDS = {
    "about", "after", "again", "also", "among", "because",
    "before", "being", "between", "both", "could", "does",
    "doing", "during", "each", "from", "have", "having",
    "into", "just", "more", "most", "much", "must",
    "other", "over", "same", "should", "some", "such",
    "than", "that", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "under",
    "very", "want", "were", "what", "when", "where",
    "which", "while", "with", "would", "your",
    "company", "customer", "customers", "product",
    "proposal", "evaluate", "evaluation", "implementation",
    "development", "system", "feature",
}


def _build_company_graph_context(
    db: Session,
    company_id: str,
) -> dict:
    """
    Build historical graph context for a company's proposal.

    Graph events and relationships are returned separately from
    document-backed claims. Chronology and stored relationships
    must not be treated as independently verified causation.
    """

    graph = build_company_graph(
        db=db,
        company_id=company_id,
    )

    events = get_company_events(
        graph=graph,
        company_id=company_id,
    )

    graph_events = []

    for event in events:
        relationships = get_event_relationships(
            graph=graph,
            event_id=event["event_id"],
            direction="both",
        )

        graph_events.append({
            "event_id": event["event_id"],
            "company_id": event.get("company_id"),
            "product_name": event.get("product_name"),
            "event_type": event.get("event_type"),
            "title": event.get("title"),
            "description": event.get("description"),
            "event_date": event.get("event_date"),
            "stated_reason": event.get("stated_reason"),
            "reported_outcome": event.get("reported_outcome"),
            "evidence_classification": event.get(
                "evidence_classification"
            ),
            "extraction_confidence": event.get(
                "extraction_confidence"
            ),
            "source_ids": event.get("source_ids", []),
            "relationships": relationships,
        })

    return {
        "company_id": company_id,
        "event_count": len(graph_events),
        "events": graph_events,
        "interpretation_warning": (
            "Events are chronological historical context. "
            "Chronology does not establish causation. Stored event "
            "relationships may not have directly associated source IDs "
            "in the current database model."
        ),
    }


def _get_customer_feedback(
    db: Session,
    company_id: str,
) -> list[dict]:
    """
    Retrieve recent, processed feedback for the proposing company.

    Feedback is supplied separately from document evidence and is
    never added to the document citation source pool.
    """

    items = (
        db.query(Feedback)
        .filter(
            Feedback.company_id == company_id,
            Feedback.analysis_status == "completed",
        )
        .order_by(Feedback.collected_at.desc())
        .limit(MAX_CUSTOMER_FEEDBACK)
        .all()
    )

    if not items:
        return []

    feedback_ids = [item.id for item in items]

    topic_rows = db.execute(
        feedback_topics.select().where(
            feedback_topics.c.feedback_id.in_(feedback_ids)
        )
    ).all()

    topics_by_feedback_id: dict[str, list[str]] = {}

    for row in topic_rows:
        topics_by_feedback_id.setdefault(
            row.feedback_id,
            [],
        ).append(row.topic)

    results = []

    for item in items:
        feedback_date = (
            item.created_at_source or item.collected_at
        )

        results.append({
            "feedback_id": item.id,
            "feedback_text": item.feedback_text,
            "product_name": item.product_name,
            "sentiment": item.sentiment,
            "feedback_type": item.feedback_type,
            "rating": item.rating,
            "feedback_date": (
                feedback_date.isoformat()
                if feedback_date is not None
                else None
            ),
            "topics": sorted(
                topics_by_feedback_id.get(item.id, [])
            ),
            "source_id": item.source_id,
            "source_url": item.source_url,
            "external_reference": item.external_reference,
        })

    return results


def _get_eligible_source_ids(
    analysis_result: dict,
    evidence_scope: str,
) -> set[str]:
    """
    Return source IDs accepted by the proposal analysis service
    for the requested evidence scope.

    These sources were eligible for analysis. This does not mean
    every source was cited by a validated claim.
    """

    evidence_sources = analysis_result.get(
        "evidence_sources",
        [],
    )

    if not isinstance(evidence_sources, list):
        return set()

    return {
        item["source_id"]
        for item in evidence_sources
        if isinstance(item, dict)
        and isinstance(item.get("source_id"), str)
        and item.get("evidence_scope") == evidence_scope
    }


def _format_evidence(
    item: dict,
    scope: str,
) -> dict:
    """Format one eligible evidence passage for the API response."""

    return {
        "source_id": item["source_id"],
        "source_title": item.get("source_title"),
        "source_url": item.get("source_url"),
        "source_company_id": item.get("source_company_id"),
        "source_company_name": item.get("source_company_name"),
        "source_company_industry": item.get(
            "source_company_industry"
        ),
        "chunk_index": item.get("chunk_index"),
        "similarity": item.get("similarity"),
        "retrieved_passage": item["chunk_text"],
        "evidence_scope": scope,
        "permission_status": item.get("permission_status"),
        "evidence_classification": "unknown",
    }


def _extract_feedback_keywords(text: str) -> set[str]:
    """
    Extract meaningful words for transparent lexical feedback matching.

    This is not semantic similarity and does not establish that
    feedback represents the broader customer population.
    """

    words = set(
        re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    )

    return {
        word
        for word in words
        if len(word) >= 4
        and word not in FEEDBACK_STOPWORDS
    }


def _get_proposal_relevant_feedback(
    feedback: list[dict],
    proposal_title: str,
    proposal_description: str,
) -> list[dict]:
    """
    Select feedback with explicit lexical overlap with the proposal.

    Matching considers feedback text, product name and processed topics.
    This is a simple transparent filter, not semantic verification.
    """

    proposal_keywords = _extract_feedback_keywords(
        f"{proposal_title} {proposal_description}"
    )

    if not proposal_keywords:
        return []

    relevant_feedback = []

    for item in feedback:
        feedback_text = " ".join([
            item.get("feedback_text") or "",
            item.get("product_name") or "",
            " ".join(item.get("topics") or []),
        ])

        feedback_keywords = _extract_feedback_keywords(
            feedback_text
        )

        if proposal_keywords.intersection(feedback_keywords):
            relevant_feedback.append(item)

    return relevant_feedback


@router.post("/analyze", status_code=200)
def analyze_proposal(
    payload: ProposalAnalyzeIn,
    db: Session = Depends(get_db),
):
    company = db.get(Company, payload.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    try:
        proposal = Proposal(
            company_id=payload.company_id,
            title=payload.title,
            description=payload.description,
            status="submitted",
        )

        db.add(proposal)
        db.flush()

        query = f"{payload.title}\n{payload.description}"

        # Retrieve internal historical document chunks.
        internal_evidence = search_similar_chunks(
            db=db,
            query=query,
            company_id=payload.company_id,
            limit=20,
        )

        # Apply proposal-specific similarity threshold.
        internal_evidence = [
            item
            for item in internal_evidence
            if item.get("similarity", 0.0)
            >= PROPOSAL_INTERNAL_MIN_SIMILARITY
        ][:5]

        if not internal_evidence:
            logger.info(
                "No internal proposal evidence passed the similarity "
                "threshold (company_id=%s, threshold=%.2f).",
                payload.company_id,
                PROPOSAL_INTERNAL_MIN_SIMILARITY,
            )

        # Retrieve public evidence from other companies.
        external_evidence = search_external_public_chunks(
            db=db,
            query=query,
            exclude_company_id=payload.company_id,
            limit=12,
        )

        # Enrich internal evidence with provenance and permissions.
        for item in internal_evidence:
            item["source_company_id"] = company.id
            item["source_company_name"] = company.name

            source = db.get(SourceDocument, item["source_id"])

            if source is not None:
                item["permission_status"] = source.permission_status

        for item in external_evidence:
            item["proposing_company_id"] = payload.company_id

        # Build supplementary historical knowledge graph context.
        graph_context = _build_company_graph_context(
            db=db,
            company_id=payload.company_id,
        )

        # Retrieve customer feedback separately from documentary evidence.
        customer_feedback = _get_customer_feedback(
            db=db,
            company_id=payload.company_id,
        )

        # Select feedback relevant to the proposal topic.
        relevant_customer_feedback = _get_proposal_relevant_feedback(
            feedback=customer_feedback,
            proposal_title=payload.title,
            proposal_description=payload.description,
        )

        # Run AI proposal analysis.
        analysis_result = analyze_proposal_with_evidence(
            title=payload.title,
            description=payload.description,
            evidence_chunks=internal_evidence,
            external_evidence_chunks=external_evidence,
            graph_context=graph_context,
            customer_feedback=customer_feedback,
        )

        # Obtain independently accepted documentary source IDs.
        eligible_internal_ids = _get_eligible_source_ids(
            analysis_result,
            "internal",
        )

        eligible_external_ids = _get_eligible_source_ids(
            analysis_result,
            "external_public",
        )

        # EVIDENCE GUARD:
        # No validated documentary sources means the model's
        # recommendation cannot be accepted as the final decision.
        if not eligible_internal_ids and not eligible_external_ids:
            logger.warning(
                "No validated documentary evidence for proposal %s. "
                "Applying insufficient-evidence recommendation.",
                proposal.id,
            )

            feedback_count = len(relevant_customer_feedback)

            analysis_result["recommendation"] = (
                "Insufficient documentary evidence to recommend "
                "proceeding with implementation. Neither internal "
                "documentary evidence nor independently verified "
                "external evidence passed the source verification checks. "
                f"{feedback_count} proposal-relevant customer feedback "
                "record(s) were identified, but feedback has not been "
                "independently verified as documentary evidence. "
                "Gather relevant historical records, validate the "
                "proposal's assumptions, define measurable success "
                "criteria, and conduct an appropriate controlled "
                "evaluation before making an implementation decision."
            )

            analysis_result["risks"] = [
                (
                    "There is insufficient verified documentary evidence "
                    "to establish the proposal's assumptions or expected "
                    "benefits."
                ),
                (
                    "Historical product decisions, experiments, and "
                    "outcomes relevant to the proposal may be unavailable."
                ),
                (
                    "Customer feedback, if available, has not been "
                    "independently verified and may not represent the "
                    "broader customer population."
                ),
                (
                    "Proceeding without validating assumptions and "
                    "defining measurable success criteria could result "
                    "in an implementation whose benefits are unproven."
                ),
            ]

            # Discard unsupported and unrelated model-generated claims.
            analysis_result["claims"] = []

            analysis_result["limitations"] = list(
                analysis_result.get("limitations", [])
            )

            analysis_result["limitations"].append(
                "The model-generated recommendation, risks and claims "
                "were overridden because no documentary evidence passed "
                "independent source eligibility checks."
            )

        # Only retain sources accepted by the analyzer.
        internal_evidence = [
            item
            for item in internal_evidence
            if item["source_id"] in eligible_internal_ids
        ]

        external_evidence = [
            item
            for item in external_evidence
            if item["source_id"] in eligible_external_ids
        ]

        limitations = list(analysis_result["limitations"])

        if not internal_evidence:
            limitations.append(
                "No internal documentary passages met the proposal "
                f"similarity threshold of "
                f"{PROPOSAL_INTERNAL_MIN_SIMILARITY:.2f}."
            )

        if not customer_feedback:
            limitations.append(
                "No completed customer feedback records were available "
                "for this company's proposal analysis."
            )

        if customer_feedback and not relevant_customer_feedback:
            limitations.append(
                "No customer feedback with explicit lexical overlap "
                "with the proposal title or description was identified."
            )

        if relevant_customer_feedback:
            limitations.append(
                "Proposal-relevant feedback was selected using lexical "
                "keyword matching. This is not semantic verification. "
                "Its source URLs and representativeness have not been "
                "independently verified."
            )

        if graph_context["event_count"] > 0:
            limitations.append(
                "Historical knowledge graph context was supplied as "
                "supplementary reasoning context. It is not "
                "document-backed evidence and cannot independently "
                "establish factual claims or support source citations."
            )

        # Persist the final analysis.
        analysis = ProposalAnalysis(
            proposal_id=proposal.id,
            status=analysis_result["status"],
            recommendation=analysis_result["recommendation"],
            risks=analysis_result["risks"],
            limitations=limitations,
            completed_at=None,
        )

        db.add(analysis)
        db.flush()

        analysis.completed_at = datetime.now(timezone.utc)
        db.flush()

        # Persist only source-linked claims.
        # Customer feedback is not stored as documentary evidence.
        persisted_pairs = set()

        for claim in analysis_result.get("claims", []):
            for source_id in claim["source_ids"]:
                pair = (claim["statement"], source_id)

                if pair in persisted_pairs:
                    continue

                persisted_pairs.add(pair)

                db.add(
                    AnalysisEvidence(
                        analysis_id=analysis.id,
                        source_id=source_id,
                        event_id=None,
                        claim=claim["statement"],
                        evidence_classification="unknown",
                    )
                )

        db.commit()

        internal_response = [
            _format_evidence(item, "internal")
            for item in internal_evidence
        ]

        external_response = [
            _format_evidence(item, "external")
            for item in external_evidence
        ]

        return {
            "proposal_id": proposal.id,
            "analysis_id": analysis.id,
            "status": analysis.status,
            "recommendation": analysis.recommendation,
            "risks": analysis.risks,
            "limitations": limitations,
            "claims": analysis_result.get("claims", []),
            "internal_evidence": internal_response,
            "external_evidence": external_response,
            "customer_feedback_context": {
                "feedback_count": len(relevant_customer_feedback),
                "total_company_feedback_available": len(
                    customer_feedback
                ),
                "feedback": relevant_customer_feedback,
                "interpretation_warning": (
                    "Customer feedback is a separate signal of customer "
                    "experiences and needs. It is not documentary proof "
                    "of product events, business outcomes or causation. "
                    "Sentiment and topic labels are heuristic. "
                    "Feedback source provenance has not necessarily "
                    "been independently verified."
                ),
            },
            "company_knowledge_context": graph_context,
            "evidence": internal_response + external_response,
        }

    except (EmbeddingError, ProposalAnalysisError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=f"Proposal analysis service unavailable: {exc}",
        ) from exc

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise


@router.get("/{analysis_id}", status_code=200)
def get_proposal_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
):
    analysis = db.get(ProposalAnalysis, analysis_id)

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Proposal analysis not found",
        )

    proposal = db.get(Proposal, analysis.proposal_id)

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Associated proposal not found",
        )

    evidence_rows = (
        db.query(AnalysisEvidence, SourceDocument, Company)
        .join(
            SourceDocument,
            AnalysisEvidence.source_id == SourceDocument.id,
        )
        .join(
            Company,
            SourceDocument.company_id == Company.id,
        )
        .filter(AnalysisEvidence.analysis_id == analysis.id)
        .all()
    )

    claims_by_statement = {}

    for record, source, source_company in evidence_rows:
        statement = record.claim

        if statement not in claims_by_statement:
            claims_by_statement[statement] = {
                "statement": statement,
                "type": "source_linked_claim",
                "source_ids": [],
                "sources": [],
                "evidence_status": "cited_context",
                "evidence_classification": record.evidence_classification,
                "evidence_scope": "unknown",
            }

        claim = claims_by_statement[statement]

        if source.id not in claim["source_ids"]:
            claim["source_ids"].append(source.id)

            scope = (
                "internal"
                if source.company_id == proposal.company_id
                else (
                    "external"
                    if source.permission_status == "public"
                    else "unknown"
                )
            )

            claim["sources"].append({
                "source_id": source.id,
                "source_title": source.title,
                "source_url": source.url,
                "source_company_id": source_company.id,
                "source_company_name": source_company.name,
                "evidence_scope": scope,
                "permission_status": source.permission_status,
            })

    # Derive overall scope from saved source references.
    for claim in claims_by_statement.values():
        scopes = {
            source["evidence_scope"]
            for source in claim["sources"]
        }

        if scopes == {"internal"}:
            claim["evidence_scope"] = "internal"
        elif scopes == {"external"}:
            claim["evidence_scope"] = "external"
        elif scopes == {"internal", "external"}:
            claim["evidence_scope"] = "mixed"

    saved_claims = list(claims_by_statement.values())

    return {
        "analysis_id": analysis.id,
        "status": analysis.status,
        "created_at": analysis.created_at,
        "completed_at": analysis.completed_at,
        "proposal": {
            "id": proposal.id,
            "company_id": proposal.company_id,
            "title": proposal.title,
            "description": proposal.description,
            "status": proposal.status,
        },
        "recommendation": analysis.recommendation,
        "risks": analysis.risks,
        "limitations": analysis.limitations,
        "claims": saved_claims,
    }
