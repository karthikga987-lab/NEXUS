
import logging
import os
import re
import time

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.core.local_access import require_local_internal_access
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
from app.intelligence.knowledge_retrieval import append_relevant_knowledge_item_passages
from app.intelligence.proposal_analysis import (
    ProposalAnalysisError,
    analyze_proposal_with_evidence,
    generate_targeted_research_queries,
)

from app.research.competitors import discover_and_ingest_competitors

from app.knowledge_graph.builder import build_company_graph
from app.knowledge_graph.traversal import (
    get_company_events,
    get_event_relationships,
)


logger = logging.getLogger("uvicorn.error")

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


@router.get("/company/{company_id}", status_code=200)
def list_company_proposals(
    company_id: str,
    db: Session = Depends(get_db),
):
    """List persisted proposals and their analysis IDs for one company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    proposals = (
        db.query(Proposal)
        .filter(Proposal.company_id == company_id)
        .order_by(Proposal.created_at.desc())
        .all()
    )
    proposal_ids = [proposal.id for proposal in proposals]
    if not proposal_ids:
        return []

    analyses = (
        db.query(ProposalAnalysis)
        .filter(ProposalAnalysis.proposal_id.in_(proposal_ids))
        .order_by(ProposalAnalysis.created_at.desc())
        .all()
    )
    analysis_ids = [analysis.id for analysis in analyses]
    restricted_analysis_ids = set()
    if analysis_ids:
        restricted_analysis_ids = {
            row[0]
            for row in (
                db.query(AnalysisEvidence.analysis_id)
                .join(
                    SourceDocument,
                    AnalysisEvidence.source_id == SourceDocument.id,
                )
                .filter(
                    AnalysisEvidence.analysis_id.in_(analysis_ids),
                    SourceDocument.permission_status != "public",
                )
                .distinct()
                .all()
            )
        }

    analyses_by_proposal = {}
    for analysis in analyses:
        accessible = analysis.id not in restricted_analysis_ids
        item = {
            "id": analysis.id,
            "status": analysis.status if accessible else "restricted",
            "accessible": accessible,
            "created_at": analysis.created_at,
            "completed_at": analysis.completed_at,
        }
        if accessible:
            item.update({
                "recommendation": analysis.recommendation,
                "risks": analysis.risks,
                "limitations": analysis.limitations,
            })
        analyses_by_proposal.setdefault(analysis.proposal_id, []).append(item)

    return [
        {
            "id": proposal.id,
            "company_id": proposal.company_id,
            "title": proposal.title,
            "description": proposal.description,
            "status": proposal.status,
            "workflow_status": (
                "completed"
                if any(
                    analysis["accessible"]
                    and analysis["status"] == "completed"
                    for analysis in analyses_by_proposal.get(proposal.id, [])
                )
                else proposal.status
            ),
            "created_at": proposal.created_at,
            "updated_at": proposal.updated_at,
            "analyses": analyses_by_proposal.get(proposal.id, []),
        }
        for proposal in proposals
    ]

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
    public_only: bool = False,
) -> list[dict]:
    """
    Retrieve recent, processed feedback for the proposing company.

    When public_only is True, only feedback linked to public source
    documents is returned. This mode is used by unauthenticated
    saved-analysis retrieval.
    """

    query = db.query(Feedback).filter(
        Feedback.company_id == company_id,
        Feedback.analysis_status == "completed",
    )

    if public_only:
        query = (
            query.join(
                SourceDocument,
                Feedback.source_id == SourceDocument.id,
            )
            .filter(SourceDocument.permission_status == "public")
        )

    items = (
        query
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
        topics_by_feedback_id.setdefault(row.feedback_id, []).append(row.topic)

    results = []

    for item in items:
        feedback_date = item.created_at_source or item.collected_at

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
            "topics": sorted(topics_by_feedback_id.get(item.id, [])),
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
        "evidence_origin": item.get("evidence_origin"),
        **{
            key: item.get(key)
            for key in (
                "proposal_relevance",
                "proposal_relevance_reason",
                "proposal_aspect",
            )
            if item.get(key) is not None
        },
    }


def _saved_analysis_source_scope(source: SourceDocument, proposal: Proposal) -> str:
    """Classify persisted public citations by provenance, not ownership alone."""
    if source.permission_status != "public":
        return "unknown"
    if source.company_id == proposal.company_id:
        return "public_company"
    return "external"


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
    request: Request = None,
):
    company = db.get(Company, payload.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    if payload.include_authorized_internal:
        if request is None:
            raise HTTPException(status_code=403, detail="Authorized internal evidence is only available through the trusted local API.")
        require_local_internal_access(request)

    request_started = time.perf_counter()

    try:
        proposal = Proposal(
            company_id=payload.company_id,
            title=payload.title,
            description=payload.description,
            status="submitted",
        )

        db.add(proposal)
        db.flush()

        # Persist the submitted proposal before starting independent
        # research. This releases SQLite's write transaction before
        # the competitor session attempts to write.
        db.commit()

        query = f"{payload.title}\n{payload.description}"

        # Retrieve internal historical document chunks.
        stage_started = time.perf_counter()

        internal_evidence = search_similar_chunks(
            db=db,
            query=query,
            company_id=payload.company_id,
            limit=20,
            include_authorized_internal=payload.include_authorized_internal,
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

        logger.info(
            "Proposal timing | internal_retrieval=%.2fs",
            time.perf_counter() - stage_started,
        )

        external_research = {
            "status": "unavailable",
            "requested": payload.include_fresh_external_research,
            "evidence_origin": "unavailable",
            "companies_discovered": 0,
            "companies_processed": 0,
            "sources_collected": 0,
            "sources_processed": 0,
            "cached_results_used": 0,
            "errors": [],
            "companies": [],
        }

        # Use eligible cached evidence immediately by default. Fresh public
        # competitor research is an explicit opt-in and is bounded by the
        # existing search/fetch timeouts.
        stage_started = time.perf_counter()
        external_evidence = search_external_public_chunks(
            db=db,
            query=query,
            exclude_company_id=payload.company_id,
            limit=12,
        )

        cached_source_ids = {
            item.get("source_id")
            for item in external_evidence
            if item.get("source_id")
        }

        if payload.include_fresh_external_research:
            competitor_db = SessionLocal()
            try:
                competitor_company = competitor_db.get(
                    Company,
                    payload.company_id,
                )
                if competitor_company is None:
                    raise ValueError(
                        "Proposal company was not found in the research session."
                    )

                external_research = discover_and_ingest_competitors(
                    db=competitor_db,
                    proposal_company=competitor_company,
                    proposal_title=payload.title,
                    proposal_description=payload.description,
                    query_generator=generate_targeted_research_queries,
                )
                external_research["requested"] = True
            except Exception as exc:
                logger.exception("External competitor research failed")
                try:
                    competitor_db.rollback()
                except Exception:
                    logger.exception(
                        "Could not roll back competitor research session"
                    )
                external_research["status"] = "failed"
                external_research["requested"] = True
                external_research["errors"] = [str(exc)[:250]]
            finally:
                competitor_db.close()

            logger.info(
                "Proposal timing | competitor_research=%.2fs",
                time.perf_counter() - stage_started,
            )

            # Requery after collection. If search/embedding fails, cached
            # results remain usable for the current partial analysis.
            try:
                external_evidence = search_external_public_chunks(
                    db=db,
                    query=query,
                    exclude_company_id=payload.company_id,
                    limit=12,
                )
            except EmbeddingError:
                if not external_evidence:
                    raise

            new_source_ids = {
                item.get("source_id")
                for item in external_evidence
                if item.get("source_id") not in cached_source_ids
            }
            for item in external_evidence:
                item["evidence_origin"] = (
                    "newly_collected"
                    if item.get("source_id") in new_source_ids
                    else "cached"
                )
            external_research["cached_results_used"] = sum(
                item.get("evidence_origin") == "cached"
                for item in external_evidence
            )
            if new_source_ids:
                external_research["evidence_origin"] = (
                    "cached_and_new" if cached_source_ids else "newly_collected"
                )
            elif external_evidence:
                external_research["evidence_origin"] = "cached"
            else:
                external_research["evidence_origin"] = "unavailable"
        else:
            external_research["status"] = (
                "cached_only" if external_evidence else "unavailable"
            )
            external_research["evidence_origin"] = (
                "cached" if external_evidence else "unavailable"
            )
            external_research["cached_results_used"] = len(external_evidence)
            for item in external_evidence:
                item["evidence_origin"] = "cached"

        logger.info(
            "Proposal timing | external_evidence_retrieval=%.2fs "
            "(results=%s)",
            time.perf_counter() - stage_started,
            len(external_evidence),
        )

        # Enrich internal evidence with provenance and permissions.
        for item in internal_evidence:
            item["source_company_id"] = company.id
            item["source_company_name"] = company.name

            source = db.get(SourceDocument, item["source_id"])

            if source is not None:
                item["permission_status"] = source.permission_status
                item["evidence_scope"] = (
                    "authorized_internal"
                    if source.permission_status == "authorized_internal"
                    else "public_company"
                )
                metadata = source.source_metadata if isinstance(source.source_metadata, dict) else {}
                item["evidence_origin"] = metadata.get(
                    "evidence_origin",
                    "authorized_internal" if source.permission_status == "authorized_internal" else "public_company",
                )

        for item in external_evidence:
            item["proposing_company_id"] = payload.company_id

        internal_evidence = append_relevant_knowledge_item_passages(
            db,
            company_id=payload.company_id,
            query=query,
            retrieved_passages=internal_evidence,
            include_authorized_internal=payload.include_authorized_internal,
        )

        # Build supplementary historical knowledge graph context.
        stage_started = time.perf_counter()

        graph_context = _build_company_graph_context(
            db=db,
            company_id=payload.company_id,
        )

        logger.info(
            "Proposal timing | graph_retrieval=%.2fs",
            time.perf_counter() - stage_started,
        )

        # Retrieve customer feedback separately from documentary evidence.
        stage_started = time.perf_counter()

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

        logger.info(
            "Proposal timing | feedback_retrieval_and_filtering=%.2fs "
            "(total=%s, relevant=%s)",
            time.perf_counter() - stage_started,
            len(customer_feedback),
            len(relevant_customer_feedback),
        )

        # Run AI proposal analysis.
        stage_started = time.perf_counter()

        analysis_result = analyze_proposal_with_evidence(
            title=payload.title,
            description=payload.description,
            evidence_chunks=internal_evidence,
            external_evidence_chunks=external_evidence,
            graph_context=graph_context,
            customer_feedback=relevant_customer_feedback,
            proposing_company_name=company.name,
        )

        logger.info(
            "Proposal timing | ai_analysis=%.2fs",
            time.perf_counter() - stage_started,
        )

        # Obtain independently accepted documentary source IDs.
        eligible_internal_ids = set().union(
            _get_eligible_source_ids(analysis_result, "internal"),
            _get_eligible_source_ids(analysis_result, "public_company"),
            _get_eligible_source_ids(analysis_result, "authorized_internal"),
            _get_eligible_source_ids(analysis_result, "company"),
        )

        eligible_external_ids = _get_eligible_source_ids(
            analysis_result,
            "external_public",
        )
        relevance_by_source_id = {
            item.get("source_id"): {
                key: item.get(key)
                for key in (
                    "proposal_relevance",
                    "proposal_relevance_reason",
                    "proposal_aspect",
                )
                if item.get(key) is not None
            }
            for item in analysis_result.get("evidence_sources", [])
            if isinstance(item, dict) and item.get("source_id")
        }
        for item in external_evidence:
            item.update(relevance_by_source_id.get(item.get("source_id"), {}))

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

        if external_research["status"] == "cached_only":
            limitations.append(
                "Fresh external research was not requested; analysis uses "
                "only relevant public evidence already stored in NEXUS."
            )
        elif external_research["status"] == "unavailable":
            limitations.append(
                "No relevant cached external public evidence was available. "
                "Fresh external research was not requested."
            )
        elif external_research["status"] not in {"completed", "partial"}:
            limitations.append(
                "Fresh external public research did not complete; any "
                "eligible cached evidence remains available for this analysis."
            )

        if (
            payload.include_fresh_external_research
            and external_research.get("companies_processed", 0) == 0
        ):
            limitations.append(
                "No new external companies were successfully processed "
                "during this proposal analysis."
            )

        if not internal_evidence:
            limitations.append(
                "No same-company documentary passages met the proposal "
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
        stage_started = time.perf_counter()

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

        logger.info(
            "Proposal timing | finalization_and_persistence=%.2fs",
            time.perf_counter() - stage_started,
        )

        logger.info(
            "Proposal timing | total_until_commit=%.2fs "
            "(proposal_id=%s)",
            time.perf_counter() - request_started,
            proposal.id,
        )

        internal_response = [
            _format_evidence(item, item.get("evidence_scope", "public_company"))
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
            "external_research": external_research,
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

    # Do not expose saved analyses backed by private or internal sources
    # through this unauthenticated endpoint.
    if any(
        source.permission_status != "public"
        for _, source, _ in evidence_rows
    ):
        raise HTTPException(
            status_code=404,
            detail="Proposal analysis not found",
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

            scope = _saved_analysis_source_scope(source, proposal)

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

        if scopes == {"public_company"}:
            claim["evidence_scope"] = "public_company"
        elif scopes == {"external"}:
            claim["evidence_scope"] = "external"
        elif scopes == {"public_company", "external"}:
            claim["evidence_scope"] = "mixed"

    saved_claims = list(claims_by_statement.values())

    # Rebuild the public company knowledge graph from current persisted data.
    # The graph builder filters event and relationship sources by permission.
    company_knowledge_context = _build_company_graph_context(
        db=db,
        company_id=proposal.company_id,
    )

    company_knowledge_context["interpretation_warning"] += (
        " This context was refreshed from currently stored public company "
        "records when the saved analysis was reopened; it is not an original "
        "analysis-time snapshot."
    )

    # Only retrieve feedback explicitly linked to public source documents.
    public_feedback = _get_customer_feedback(
        db=db,
        company_id=proposal.company_id,
        public_only=True,
    )

    relevant_public_feedback = _get_proposal_relevant_feedback(
        feedback=public_feedback,
        proposal_title=proposal.title,
        proposal_description=proposal.description,
    )

    public_feedback_count = (
        db.query(Feedback.id)
        .join(
            SourceDocument,
            Feedback.source_id == SourceDocument.id,
        )
        .filter(
            Feedback.company_id == proposal.company_id,
            Feedback.analysis_status == "completed",
            SourceDocument.permission_status == "public",
        )
        .count()
    )

    customer_feedback_context = {
        "feedback_count": len(relevant_public_feedback),
        "total_company_feedback_available": public_feedback_count,
        "feedback": relevant_public_feedback,
        "interpretation_warning": (
            "This feedback was refreshed from currently stored records "
            "linked to public source documents when the saved analysis "
            "was reopened. It is not an original analysis-time snapshot. "
            "Feedback is a separate customer signal, not documentary proof "
            "of product events, business outcomes or causation. "
            "Keyword matching does not establish semantic relevance or "
            "representativeness."
        ),
    }

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
        "company_knowledge_context": company_knowledge_context,
        "customer_feedback_context": customer_feedback_context,
        "context_retrieval_mode": "refreshed_current_public_company_data",
    }
