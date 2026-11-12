from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import feedback as feedback_route
from app.api.routes import proposals as proposals_route
from app.db.session import Base, get_db
from app.feedback.analyzer import analyze_feedback
from app.intelligence import embeddings, ingestion
from app.intelligence.rag import answer_with_evidence
from app.main import app
from app.models import Company, DocumentEmbedding, ProductEvent, SourceDocument
from app.models.entities import Feedback, event_sources
from app.research.persistence import save_source
from app.research import service as research_service
from app.research import discovery as research_discovery
from app.schemas.contracts import FeedbackCreate, ProposalAnalyzeIn


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nexus_integration.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session, factory
    finally:
        session.close()
        engine.dispose()


def create_company(db):
    company = Company(name="Synthetic Acme", website="https://acme.example")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def test_persisted_source_ingests_to_event_and_embedding(db, monkeypatch):
    session, _ = db
    company = create_company(session)
    text = (
        "Acme announced the launch of Acme Pay on March 3, 2024. "
        "The product is designed to simplify checkout for small businesses."
    )
    source, created = save_source(
        session,
        company.id,
        "https://acme.example/news/acme-pay",
        {"title": "Synthetic Acme Pay announcement", "content_text": text},
    )
    assert created is True

    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda chunks: [[1.0] + [0.0] * 767 for _ in chunks],
    )
    monkeypatch.setattr(
        ingestion,
        "extract_events",
        lambda **kwargs: [{
            "product_name": "Acme Pay",
            "event_type": "product_launch",
            "title": "Acme Pay launched",
            "event_date": "2024-03-03",
            "stated_reason": "Simplify checkout for small businesses",
            "outcome_summary": None,
            "evidence_status": "documented",
            "extraction_confidence": 0.9,
            "evidence_quote": "Acme announced the launch of Acme Pay on March 3, 2024.",
        }],
    )

    result = ingestion.process_company_sources(
        db=session,
        company_id=company.id,
        source_ids=[source.id],
    )

    assert result["status"] == "completed"
    assert result["counts"]["processed"] == 1
    assert session.get(SourceDocument, source.id).processing_status == "processed"
    event = session.query(ProductEvent).filter_by(company_id=company.id).one()
    assert event.product_name == "Acme Pay"
    assert session.execute(
        select(event_sources).where(event_sources.c.event_id == event.id)
    ).first() is not None
    vector = session.query(DocumentEmbedding).filter_by(source_id=source.id).one()
    assert vector.chunk_text == text
    assert len(vector.embedding) == 768


def test_semantic_retrieval_rag_reports_unanswered_aspect(db, monkeypatch):
    session, _ = db
    company = create_company(session)
    passage = (
        "Acme announced the launch of Acme Pay on March 3, 2024. "
        "The company said it was designed to simplify checkout for small businesses."
    )
    source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/news/acme-pay",
        title="Acme Pay launch",
        content_text=passage,
        permission_status="public",
        source_type="press_release",
        collected_at=datetime.now(timezone.utc),
    )
    session.add(source)
    session.flush()
    session.add(DocumentEmbedding(
        source_id=source.id,
        chunk_index=0,
        chunk_text=passage,
        embedding=[1.0] + [0.0] * 767,
        model_name=embeddings.EMBEDDING_MODEL,
    ))
    session.commit()
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: [[1.0] + [0.0] * 767 for _ in texts],
    )

    answer = answer_with_evidence(
        session,
        company.id,
        "What product was launched, why, and what result was reported?",
    )

    assert answer["answer_status"] == "partially_answered", answer
    aspect_states = {row["aspect"]: row["status"] for row in answer["requested_aspects"]}
    assert aspect_states["event"] == "supported"
    assert aspect_states["reason"] == "supported"
    assert aspect_states["outcome"] == "not_found_in_verified_evidence"
    assert answer["verified_claims"]
    assert "result" in answer["answer"].casefold() or "outcome" in answer["answer"].casefold()


def test_rag_retrieves_verified_shutdown_date_from_help_page(db, monkeypatch):
    session, _ = db
    company = create_company(session)
    passage = (
        "SYNTHETIC TEST FIXTURE. The Acme service shut down on January 18, 2023."
    )
    source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/help/synthetic-shutdown",
        title="Synthetic Acme Help page shutdown information",
        content_text=passage,
        permission_status="public",
        source_type="official_blog",
        collected_at=datetime.now(timezone.utc),
    )
    session.add(source)
    session.flush()
    session.add(DocumentEmbedding(
        source_id=source.id,
        chunk_index=0,
        chunk_text=passage,
        embedding=[1.0] + [0.0] * 767,
        model_name=embeddings.EMBEDDING_MODEL,
    ))
    session.commit()
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: [[1.0] + [0.0] * 767 for _ in texts],
    )

    answer = answer_with_evidence(
        session,
        company.id,
        "What date did Synthetic Acme shut down according to the Acme Help page?",
    )

    assert answer["answer_status"] == "answered_with_verified_evidence", answer
    assert {row["aspect"]: row["status"] for row in answer["requested_aspects"]} == {
        "date": "supported",
    }
    claim = next(
        claim for claim in answer["verified_claims"]
        if "shut down" in claim["statement"].casefold()
    )
    expected_claim = "The Acme service shut down on January 18, 2023."
    assert claim["statement"] == expected_claim
    assert claim["citations"][0]["source_id"] == str(source.id)
    assert claim["citations"][0]["source_url"] == source.url
    assert claim["citations"][0]["supporting_quote"] == expected_claim


def test_semantic_retrieval_rag_covers_each_requested_experiment_fact(db, monkeypatch):
    session, _ = db
    company = create_company(session)
    passage = (
        "In a clearly labelled synthetic experiment, the team compared the "
        "original PulseBoard dashboard with a redesigned dashboard. "
        "The report stated that 40 fictional pilot users participated in the "
        "two-week test. "
        "The measured task completion time fell from 90 seconds to 55 seconds."
    )
    source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/synthetic/pulseboard-test",
        title="Synthetic PulseBoard experiment report",
        content_text=passage,
        permission_status="public",
        source_type="press_release",
        collected_at=datetime.now(timezone.utc),
    )
    session.add(source)
    session.flush()
    session.add(DocumentEmbedding(
        source_id=source.id,
        chunk_index=0,
        chunk_text=passage,
        embedding=[1.0] + [0.0] * 767,
        model_name=embeddings.EMBEDDING_MODEL,
    ))
    session.commit()
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: [[1.0] + [0.0] * 767 for _ in texts],
    )

    answer = answer_with_evidence(
        session,
        company.id,
        "Which PulseBoard dashboard versions were compared, how many users "
        "participated, and what measured outcome was reported?",
    )

    aspect_states = {
        row["aspect"]: row["status"] for row in answer["requested_aspects"]
    }
    assert aspect_states == {
        "comparison": "supported",
        "outcome": "supported",
        "participation": "supported",
    }, answer
    assert answer["answer_status"] == "answered_with_verified_evidence"
    assert answer["verified_claims"]
    assert all(claim["citations"] for claim in answer["verified_claims"])
    assert "original pulseboard dashboard" in answer["answer"].casefold()
    assert "40 fictional pilot users" in answer["answer"].casefold()
    assert "90 seconds to 55 seconds" in answer["answer"].casefold()


def test_semantic_retrieval_does_not_treat_result_label_as_outcome(db, monkeypatch):
    session, _ = db
    company = create_company(session)
    passage = (
        "Acme launched Acme Pay for small businesses. "
        "The company said it was designed to simplify checkout. "
        "The report described this as a result of the fictional experiment."
    )
    source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/news/acme-pay-synthetic",
        title="Synthetic Acme Pay launch",
        content_text=passage,
        permission_status="public",
        source_type="press_release",
        collected_at=datetime.now(timezone.utc),
    )
    session.add(source)
    session.flush()
    session.add(DocumentEmbedding(
        source_id=source.id,
        chunk_index=0,
        chunk_text=passage,
        embedding=[1.0] + [0.0] * 767,
        model_name=embeddings.EMBEDDING_MODEL,
    ))
    session.commit()
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: [[1.0] + [0.0] * 767 for _ in texts],
    )

    answer = answer_with_evidence(
        session,
        company.id,
        "What product was launched, why, and what result was reported?",
    )

    aspect_states = {row["aspect"]: row["status"] for row in answer["requested_aspects"]}
    assert answer["answer_status"] == "partially_answered", answer
    assert aspect_states["event"] == "supported"
    assert aspect_states["reason"] == "supported"
    assert aspect_states["outcome"] == "not_found_in_verified_evidence"


def test_feedback_submission_persists_and_appears_in_analysis(db):
    session, _ = db
    company = create_company(session)
    response = feedback_route.create_feedback(
        FeedbackCreate(
            company_id=company.id,
            text="The checkout is confusing and slow.",
            product_name="Acme Pay",
        ),
        session,
    )

    assert response["status"] == "stored"
    stored = session.query(Feedback).filter_by(company_id=company.id).one()
    assert stored.feedback_text == "The checkout is confusing and slow."
    analysis = feedback_route.feedback_analysis(company.id, session)
    assert analysis["total_feedback"] == 1
    assert analysis["sentiment_distribution"] == {"negative": 1}
    assert analysis["topic_distribution"]


def test_feedback_is_retrieved_as_proposal_context(db, monkeypatch):
    session, factory = db
    company = create_company(session)
    source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/checkout",
        title="Synthetic checkout documentation",
        content_text="Synthetic product documentation for checkout.",
        permission_status="public",
        source_type="official_blog",
    )
    session.add(source)
    session.commit()

    feedback_route.create_feedback(
        FeedbackCreate(
            company_id=company.id,
            text="Checkout is confusing and slow.",
            product_name="Acme Pay",
        ),
        session,
    )

    monkeypatch.setattr(proposals_route, "SessionLocal", factory)
    monkeypatch.setattr(
        proposals_route,
        "search_similar_chunks",
        lambda **kwargs: [{
            "source_id": source.id,
            "source_title": source.title,
            "source_url": source.url,
            "chunk_text": source.content_text,
            "similarity": 0.95,
        }],
    )
    monkeypatch.setattr(proposals_route, "search_external_public_chunks", lambda **kwargs: [])
    monkeypatch.setattr(
        proposals_route,
        "discover_and_ingest_competitors",
        lambda **kwargs: {
            "status": "completed",
            "companies_discovered": 0,
            "companies_processed": 0,
            "sources_collected": 0,
            "sources_processed": 0,
            "errors": [],
            "companies": [],
        },
    )

    received_feedback = {}

    def analyze(**kwargs):
        received_feedback["items"] = kwargs["customer_feedback"]
        received_feedback["evidence"] = kwargs["evidence_chunks"]
        return {
            "status": "completed",
            "recommendation": "Use a measured checkout simplification experiment.",
            "risks": [],
            "limitations": [],
            "claims": [],
            "evidence_sources": [{
                "source_id": source.id,
                "evidence_scope": "internal",
            }],
        }

    monkeypatch.setattr(proposals_route, "analyze_proposal_with_evidence", analyze)
    result = proposals_route.analyze_proposal(
        ProposalAnalyzeIn(
            company_id=company.id,
            title="Simplify checkout",
            description="Reduce confusing checkout steps for Acme Pay customers.",
        ),
        session,
    )

    assert result["customer_feedback_context"]["feedback_count"] == 1
    assert received_feedback["evidence"][0]["evidence_scope"] == "public_company"
    assert received_feedback["evidence"][0]["evidence_origin"] == "public_company"
    assert received_feedback["items"][0]["feedback_text"] == "Checkout is confusing and slow."
    assert received_feedback["items"][0]["topics"]
    assert result["customer_feedback_context"]["feedback"][0]["feedback_id"]


def test_proposal_analysis_uses_cached_external_evidence_without_network(
    db,
    monkeypatch,
):
    session, _ = db
    company = create_company(session)
    competitor = Company(
        name="Synthetic Public Comparator",
        website="https://comparator.example",
    )
    session.add(competitor)
    session.commit()

    source = SourceDocument(
        company_id=competitor.id,
        url="https://comparator.example/launch",
        title="Synthetic public launch report",
        publisher="comparator.example",
        source_type="news",
        content_text="The comparator introduced a same-day delivery option.",
        content_hash="synthetic-public-source-hash",
        permission_status="public",
        processing_status="processed",
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    cached = {
        "source_id": source.id,
        "source_title": source.title,
        "source_url": source.url,
        "source_company_id": competitor.id,
        "source_company_name": competitor.name,
        "chunk_index": 0,
        "chunk_text": source.content_text,
        "similarity": 0.91,
        "permission_status": "public",
        "evidence_scope": "external_public",
    }
    monkeypatch.setattr(
        proposals_route,
        "search_similar_chunks",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        proposals_route,
        "search_external_public_chunks",
        lambda **kwargs: [dict(cached)],
    )

    def unexpected_live_research(**kwargs):
        raise AssertionError("Default proposal analysis must not crawl the web")

    monkeypatch.setattr(
        proposals_route,
        "discover_and_ingest_competitors",
        unexpected_live_research,
    )

    def analyze(**kwargs):
        assert kwargs["external_evidence_chunks"][0]["source_id"] == source.id
        return {
            "status": "completed",
            "recommendation": "Use a controlled, measured pilot.",
            "risks": [],
            "limitations": [],
            "claims": [],
            "evidence_sources": [{
                "source_id": source.id,
                "evidence_scope": "external_public",
            }],
        }

    monkeypatch.setattr(
        proposals_route,
        "analyze_proposal_with_evidence",
        analyze,
    )

    result = proposals_route.analyze_proposal(
        ProposalAnalyzeIn(
            company_id=company.id,
            title="A synthetic delivery pilot",
            description=(
                "Evaluate a controlled delivery option pilot for selected users."
            ),
        ),
        session,
    )

    assert result["external_research"]["status"] == "cached_only"
    assert result["external_research"]["evidence_origin"] == "cached"
    assert result["external_research"]["cached_results_used"] == 1
    assert result["external_evidence"][0]["source_id"] == source.id
    assert result["external_evidence"][0]["evidence_origin"] == "cached"


def test_feedback_classifier_generic_topic_and_heuristic_limits():
    generic = analyze_feedback("The product is purple on Tuesdays.")
    assert generic["topics"] == ["general"]
    assert generic["sentiment"] == "neutral"
    assert generic["feedback_type"] == "other"

    blank = analyze_feedback("   ")
    assert blank["sentiment"] == "unknown"
    assert blank["topics"] == ["general"]

    # These labels are keyword heuristics; text with no listed sentiment
    # terms remains neutral rather than receiving model-inferred polarity.
    assert analyze_feedback("It works as expected.")["sentiment"] == "neutral"

    leaking_cap = analyze_feedback(
        "[SYNTHETIC TEST] The bottle cap leaks after use."
    )
    assert leaking_cap["sentiment"] == "negative"
    assert "reliability" in leaking_cap["topics"]
    assert leaking_cap["feedback_type"] == "complaint"


def test_research_and_ingestion_http_workflow_uses_shared_company_records(
    tmp_path,
    monkeypatch,
):
    """Exercise the research and ingestion routes through FastAPI on a temp DB."""
    engine = create_engine(f"sqlite:///{tmp_path / 'route_workflow.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    previous_overrides = app.dependency_overrides.copy()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    html = (
        "<html><head><title>Synthetic Acme Pay product update</title>"
        "<meta name='description' content='Synthetic product launch notice'></head>"
        "<body><main><h1>Acme Pay launched</h1>"
        "<p>Acme announced the launch of Acme Pay on March 3, 2024. "
        "The company said it created the service to simplify checkout for "
        "small businesses. This is a clearly labelled synthetic fixture, "
        "not a real company announcement.</p>"
        f"<p>{'Synthetic product and company information for integration coverage. ' * 25}</p>"
        "</main></body></html>"
    )

    monkeypatch.setattr(
        research_service,
        "discover_sources",
        lambda **kwargs: ["https://acme.example/news/acme-pay"],
    )
    monkeypatch.setattr(research_discovery, "search_ddgs", lambda query, max_results=5: [])
    monkeypatch.setattr(
        research_service,
        "fetch_url_with_diagnostics",
        lambda url: {"content": html, "reason": None},
    )
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda chunks: [[1.0] + [0.0] * 767 for _ in chunks],
    )
    monkeypatch.setattr(
        ingestion,
        "extract_events",
        lambda **kwargs: [{
            "product_name": "Acme Pay",
            "event_type": "product_launch",
            "title": "Acme Pay launched",
            "event_date": "2024-03-03",
            "stated_reason": "Simplify checkout for small businesses",
            "outcome_summary": None,
            "evidence_status": "documented",
            "extraction_confidence": 0.9,
            "evidence_quote": "Acme announced the launch of Acme Pay on March 3, 2024.",
        }],
    )

    try:
        with TestClient(app) as client:
            company_response = client.post(
                "/api/companies",
                json={"name": "[SYNTHETIC TEST] Acme", "website": "https://acme.example"},
            )
            assert company_response.status_code == 201, company_response.text
            company_id = company_response.json()["id"]

            research_response = client.post(
                f"/api/companies/{company_id}/research",
            )
            assert research_response.status_code == 200, research_response.text
            research = research_response.json()
            # Company creation already ran the bounded onboarding workflow.
            # A manual research retry must reuse the existing source safely.
            assert research["counts"]["created"] == 0
            assert research["counts"]["updated_or_unchanged"] == 1
            source_id = research["results"][0]["source_id"]

            processing_response = client.post(
                f"/api/ingestion/companies/{company_id}/process",
                json={"source_ids": [source_id]},
            )
            assert processing_response.status_code == 200, processing_response.text
            assert processing_response.json()["counts"]["skipped"] == 1

            sources = client.get(f"/api/companies/{company_id}/sources")
            events = client.get(f"/api/companies/{company_id}/events")
            status = client.get(f"/api/ingestion/companies/{company_id}/status")
            assert sources.status_code == events.status_code == status.status_code == 200
            assert sources.json()[0]["processing_status"] == "processed"
            assert sources.json()[0]["extracted_event_evidence"][0]["evidence_quote"] == (
                "Acme announced the launch of Acme Pay on March 3, 2024."
            )
            assert sources.json()[0]["event_date"] == "2024-03-03T00:00:00Z"
            assert events.json()[0]["source_ids"] == [source_id]
            assert status.json()["processing_status_counts"]["processed"] == 1

            with factory() as session:
                assert session.get(Company, company_id).research_status == "completed"
                assert session.query(ProductEvent).filter_by(company_id=company_id).count() == 1
                assert session.query(DocumentEmbedding).filter_by(source_id=source_id).count() >= 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
