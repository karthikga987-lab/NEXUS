from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.session import Base, get_db
from app.intelligence import embeddings, ingestion
from app.intelligence import relationship_extraction
from app.main import app
from app.models import Company, DocumentEmbedding, EventRelationship, ProductEvent, ResearchRun, SourceDocument
from app.models.entities import relationship_sources
from app.research import service as research_service


def test_company_creation_runs_research_ingestion_and_persists_evidence(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'onboarding.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    previous_overrides = app.dependency_overrides.copy()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    source_text = (
        "[SYNTHETIC TEST FIXTURE] Acme launched Acme Pay on March 3, 2024. "
        "Acme introduced Acme Pay Rewards on August 2, 2024. "
        "The March launch of Acme Pay resulted in the August introduction "
        "of Acme Pay Rewards. "
        + "Acme product information and customer service details. " * 60
    )
    relationship_quote = (
        "The March launch of Acme Pay resulted in the August introduction "
        "of Acme Pay Rewards."
    )
    source_url = "https://acme.example/news/acme-pay"

    monkeypatch.setattr(
        research_service,
        "discover_sources",
        lambda **kwargs: [source_url],
    )
    monkeypatch.setattr(
        research_service,
        "discover_company_candidates",
        lambda company, **kwargs: ([{
            "url": source_url,
            "evidence_origin": "public_company",
            "source_category": "product_announcement",
            "discovery_method": "synthetic_test_fixture",
        }], []),
    )
    monkeypatch.setattr(
        research_service,
        "fetch_url_with_diagnostics",
        lambda url: {"content": "<html>synthetic</html>", "reason": None},
    )
    monkeypatch.setattr(
        research_service,
        "extract_page",
        lambda **kwargs: {
            "title": "[SYNTHETIC TEST FIXTURE] Acme Pay launch",
            "meta_description": "Product launch and service update",
            "content_text": source_text,
        },
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
            "description": None,
            "event_date": "2024-03-03",
            "stated_reason": None,
            "outcome_summary": None,
            "evidence_status": "documented",
            "extraction_confidence": 0.9,
            "evidence_quote": "Acme launched Acme Pay on March 3, 2024.",
        }, {
            "product_name": "Acme Pay Rewards",
            "event_type": "feature_launch",
            "title": "Acme Pay Rewards introduced",
            "description": None,
            "event_date": "2024-08-02",
            "stated_reason": None,
            "outcome_summary": None,
            "evidence_status": "documented",
            "extraction_confidence": 0.9,
            "evidence_quote": "Acme introduced Acme Pay Rewards on August 2, 2024.",
        }],
    )

    def mocked_relationship_candidates(source_text, events):
        by_title = {event.title: event for event in events}
        return [{
            "from_event_id": by_title["Acme Pay launched"].id,
            "to_event_id": by_title["Acme Pay Rewards introduced"].id,
            "relation_type": "RESULTED_IN",
            "evidence_status": "documented_cause",
            "confidence": 0.9,
            "supporting_quote": relationship_quote,
            "explanation": relationship_quote,
        }]

    monkeypatch.setattr(
        relationship_extraction, "_ask_ollama", mocked_relationship_candidates
    )
    monkeypatch.setattr(
        relationship_extraction,
        "_verify_relationship_semantics",
        lambda **kwargs: (True, "semantic_verification_passed"),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/companies",
                json={"name": "[SYNTHETIC TEST FIXTURE] Acme", "website": "https://acme.example"},
            )
            assert response.status_code == 201, response.text
            company_id = response.json()["id"]

            stats = client.get(f"/api/companies/{company_id}/research-stats")
            assert stats.status_code == 200, stats.text
            assert stats.json()["research_status"] == "completed"
            counts = stats.json()["latest_run"]["counts"]
            assert counts["discovered"] == 1
            assert counts["collected"] == 1
            assert counts["ingestion_processed"] == 1
            assert counts["ingestion_events_extracted"] == 2
            assert counts["ingestion_embedding_chunks_created"] >= 1
            assert counts["ingestion_relationships_created"] == 1
            graph = client.get(f"/api/companies/{company_id}/knowledge-graph")
            assert graph.status_code == 200, graph.text
            graph_edges = graph.json()["edges"]
            assert any(
                edge.get("relation_type") == "RESULTED_IN"
                and edge.get("source_provenance_available") is True
                for edge in graph_edges
            )

            with factory() as db:
                company = db.get(Company, company_id)
                source = db.query(SourceDocument).filter_by(company_id=company_id).one()
                events = db.query(ProductEvent).filter_by(company_id=company_id).all()
                run = db.query(ResearchRun).filter_by(company_id=company_id).one()
                assert company.research_status == "completed"
                assert source.processing_status == "processed"
                assert source.source_metadata["evidence_origin"] == "public_company"
                assert len(events) == 2
                assert any(event.event_date.isoformat().startswith("2024-03-03") for event in events)
                relationship = db.query(EventRelationship).filter_by(company_id=company_id).one()
                provenance = db.execute(relationship_sources.select()).mappings().one()
                assert relationship.confidence == 0.9
                assert provenance["supporting_quote"] == relationship_quote
                assert db.query(DocumentEmbedding).filter_by(source_id=source.id).count() >= 1
                assert run.counts["ingestion_events_extracted"] == 2
                assert run.counts["ingestion_relationships_created"] == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def test_company_without_website_is_not_queued_for_research(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'onboarding_no_site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    previous_overrides = app.dependency_overrides.copy()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/companies", json={"name": "[SYNTHETIC TEST FIXTURE] No website"})
            assert response.status_code == 201, response.text
            company_id = response.json()["id"]
            stats = client.get(f"/api/companies/{company_id}/research-stats").json()
            assert stats["research_status"] == "not_started"
            assert stats["latest_run"] is None
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
