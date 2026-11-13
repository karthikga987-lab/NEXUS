from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Company, ProductEvent, Proposal, SourceDocument
from app.models.entities import (
    AnalysisEvidence,
    Feedback,
    ProposalAnalysis,
    ProposalAnalysisSnapshot,
    analysis_events,
    analysis_feedback,
)
from app.api.routes import proposals as proposals_route
from app.schemas.contracts import ProposalAnalyzeIn


def _temp_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis_snapshot.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, factory


def test_analysis_snapshot_reopens_exact_passage_and_analysis_context(
    tmp_path,
    monkeypatch,
):
    engine, factory = _temp_db(tmp_path)
    try:
        with factory() as db:
            company = Company(name="[SYNTHETIC] Snapshot Company")
            db.add(company)
            db.flush()
            source = SourceDocument(
                company_id=company.id,
                url="https://synthetic.example/old-url",
                title="[SYNTHETIC] Original source title",
                publisher="synthetic.example",
                source_type="news",
                publication_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                collected_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
                content_text=(
                    "[SYNTHETIC FIXTURE] The synthetic company introduced "
                    "a reusable bottle in 2024."
                ),
                permission_status="public",
                source_metadata={"original_url": "https://synthetic.example/original"},
                processing_status="processed",
            )
            event = ProductEvent(
                company_id=company.id,
                event_type="feature_update",
                title="[SYNTHETIC] Reusable bottle introduction",
                description="Synthetic graph context only.",
                evidence_classification="documented",
            )
            feedback = Feedback(
                company_id=company.id,
                source_id=source.id,
                source_url="https://synthetic.example/review",
                feedback_text="[SYNTHETIC FIXTURE] Customers requested a better bottle cap.",
                sentiment="neutral",
                feedback_type="feature_request",
                analysis_status="completed",
            )
            db.add_all([source, event, feedback])
            db.commit()
            company_id, source_id, event_id, feedback_id = (
                company.id, source.id, event.id, feedback.id
            )

            passage = source.content_text
            feedback_context = [{
                "feedback_id": feedback_id,
                "feedback_text": feedback.feedback_text,
                "source_id": source_id,
                "source_url": feedback.source_url,
                "topics": ["feature_request"],
            }]
            monkeypatch.setattr(
                proposals_route,
                "search_similar_chunks",
                lambda **_kwargs: [{
                    "source_id": source_id,
                    "source_title": source.title,
                    "source_url": source.url,
                    "chunk_index": 2,
                    "chunk_text": passage,
                    "similarity": 0.91,
                    "permission_status": "public",
                }],
            )
            monkeypatch.setattr(
                proposals_route,
                "search_external_public_chunks",
                lambda **_kwargs: [],
            )
            monkeypatch.setattr(
                proposals_route,
                "_build_company_graph_context",
                lambda **_kwargs: {
                    "company_id": company_id,
                    "event_count": 1,
                    "events": [{
                        "event_id": event_id,
                        "company_id": company_id,
                        "title": "[SYNTHETIC] Reusable bottle introduction",
                        "source_ids": [source_id],
                    }],
                    "interpretation_warning": "Synthetic graph context.",
                },
            )
            monkeypatch.setattr(
                proposals_route,
                "_get_customer_feedback",
                lambda **_kwargs: feedback_context,
            )
            monkeypatch.setattr(
                proposals_route,
                "_get_proposal_relevant_feedback",
                lambda **_kwargs: feedback_context,
            )
            monkeypatch.setattr(
                proposals_route,
                "analyze_proposal_with_evidence",
                lambda **_kwargs: {
                    "status": "completed",
                    "recommendation": "Synthetic recommendation for testing.",
                    "risks": ["Synthetic risk."],
                    "limitations": [],
                    "claims": [{
                        "statement": "The synthetic company introduced a reusable bottle in 2024.",
                        "type": "factual_observation",
                        "source_ids": [source_id],
                        "evidence_status": "cited_context",
                        "verification_status": "verified",
                        "evidence_scope": "public_company",
                        "supporting_evidence": [{
                            "source_id": source_id,
                            "supporting_quote": "The synthetic company introduced a reusable bottle in 2024.",
                            "verification_method": "llm_with_exact_quote_validation",
                        }],
                    }, {
                        "statement": (
                            "The synthetic reusable bottle is available for purchase "
                            "at a competitive price point."
                        ),
                        "type": "factual_observation",
                        "source_ids": [source_id],
                        "evidence_status": "cited_context",
                        "verification_status": "verified",
                        "evidence_scope": "public_company",
                        "supporting_evidence": [{
                            "source_id": source_id,
                            "supporting_quote": (
                                "The synthetic company introduced a reusable bottle in 2024."
                            ),
                            "verification_method": "llm_with_exact_quote_validation",
                        }],
                    }],
                    "evidence_sources": [{
                        "source_id": source_id,
                        "evidence_scope": "public_company",
                    }],
                },
            )

            result = proposals_route.analyze_proposal(
                ProposalAnalyzeIn(
                    company_id=company_id,
                    title="[SYNTHETIC] Reusable bottle proposal",
                    description="A labelled synthetic proposal for a reusable bottle cap improvement.",
                ),
                db,
            )
            assert result["evidence_snapshot_available"] is True
            assert result["evidence"][0]["retrieved_passage"] == passage
            assert result["evidence"][0]["source_url"] == "https://synthetic.example/original"
            unsupported_statement = (
                "The synthetic reusable bottle is available for purchase "
                "at a competitive price point."
            )
            assert unsupported_statement not in {
                claim["statement"] for claim in result["claims"]
            }
            assert result["unverified_claims"][0]["statement"] == unsupported_statement
            assert result["unverified_claims"][0]["verification_status"] == "unverified"
            analysis_id = result["analysis_id"]

            saved = db.get(ProposalAnalysisSnapshot, analysis_id)
            assert saved is not None
            assert saved.snapshot["verified_claims"][0]["supporting_evidence"][0]["supporting_quote"] == (
                "The synthetic company introduced a reusable bottle in 2024."
            )
            assert saved.snapshot["unverified_claims"][0]["statement"] == unsupported_statement
            assert saved.snapshot["unverified_claims"][0]["candidate_evidence"][0]["supporting_quote"] == (
                "The synthetic company introduced a reusable bottle in 2024."
            )
            assert db.execute(
                analysis_events.select().where(analysis_events.c.analysis_id == analysis_id)
            ).all() == [(analysis_id, event_id)]
            assert db.execute(
                analysis_feedback.select().where(analysis_feedback.c.analysis_id == analysis_id)
            ).all() == [(analysis_id, feedback_id)]
            evidence_records = db.query(AnalysisEvidence).filter_by(analysis_id=analysis_id).all()
            assert len(evidence_records) == 1
            assert evidence_records[0].claim != unsupported_statement

            # Current source metadata changes must not rewrite the saved snapshot.
            source.title = "Changed after analysis"
            source.content_text = "Changed source text after analysis."
            db.commit()

            reopened = proposals_route.get_proposal_analysis(analysis_id, db)
            assert reopened["evidence_snapshot_available"] is True
            assert reopened["evidence"][0]["source_title"] == "[SYNTHETIC] Original source title"
            assert reopened["evidence"][0]["retrieved_passage"] == passage
            assert reopened["claims"][0]["verification_status"] == "verified"
            assert reopened["unverified_claims"][0]["statement"] == unsupported_statement
            assert reopened["unverified_claims"][0]["verification_status"] == "unverified"
            assert reopened["company_knowledge_context"]["events"][0]["event_id"] == event_id
            assert reopened["customer_feedback_context"]["feedback"][0]["feedback_id"] == feedback_id
    finally:
        engine.dispose()


def test_legacy_analysis_explicitly_reports_unavailable_snapshot(tmp_path):
    engine, factory = _temp_db(tmp_path)
    try:
        with factory() as db:
            company = Company(name="[SYNTHETIC] Legacy Snapshot Company")
            db.add(company)
            db.flush()
            proposal = Proposal(
                company_id=company.id,
                title="[SYNTHETIC] Legacy proposal",
                description="A synthetic old proposal with no original snapshot.",
                status="submitted",
            )
            db.add(proposal)
            db.flush()
            analysis = ProposalAnalysis(
                proposal_id=proposal.id,
                status="completed",
                recommendation="Legacy synthetic recommendation.",
                risks=[],
                limitations=[],
            )
            db.add(analysis)
            db.commit()

            reopened = proposals_route.get_proposal_analysis(analysis.id, db)
            assert reopened["evidence_snapshot_available"] is False
            assert reopened["snapshot_warning"] == "Historical evidence snapshot unavailable."
            assert reopened["evidence"] == []
            assert reopened["context_retrieval_mode"] == "legacy_refreshed_current_public_data"
    finally:
        engine.dispose()
