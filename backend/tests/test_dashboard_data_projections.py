from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models import Company, Feedback, ResearchRun, SourceDocument
from app.models.entities import (
    KnowledgeItem,
    ProductEvent,
    event_sources,
    feedback_topics,
)


@pytest.fixture
def dashboard_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard_projections.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, factory
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def test_company_create_read_and_legacy_status_match_contract(dashboard_client):
    client, factory = dashboard_client
    created = client.post(
        "/api/companies",
        json={
            "name": "[SYNTHETIC] Projection Test Company",
            "industry": "Synthetic testing",
            "website": None,
        },
    )
    assert created.status_code == 201
    company = created.json()
    assert company["industry"] == "Synthetic testing"
    assert company["research_status"] == "not_started"
    assert company["updated_at"]

    detail = client.get(f"/api/companies/{company['id']}")
    assert detail.status_code == 200
    assert detail.json()["industry"] == "Synthetic testing"
    assert detail.json()["research_status"] == "not_started"

    with factory() as db:
        legacy = Company(
            name="[SYNTHETIC] Legacy Pending Status",
            research_status="not_started",
        )
        db.add(legacy)
        db.flush()
        db.add(ResearchRun(
            company_id=legacy.id,
            status="completed",
            counts={"collected": 2},
        ))
        db.commit()
        legacy_id = legacy.id

    assert client.get(f"/api/companies/{legacy_id}").json()["research_status"] == "completed"
    assert client.get(f"/api/companies/{legacy_id}/research-stats").json()["research_status"] == "completed"
    graph = client.get(f"/api/companies/{legacy_id}/knowledge-graph").json()
    company_node = next(node for node in graph["nodes"] if node["node_type"] == "company")
    assert company_node["research_status"] == "completed"


def test_failed_public_source_exposes_only_safe_processing_diagnostic(dashboard_client):
    client, factory = dashboard_client
    with factory() as db:
        company = Company(name="[SYNTHETIC] Source Diagnostic Company")
        db.add(company)
        db.flush()
        source = SourceDocument(
            company_id=company.id,
            url="https://example.test/synthetic-failed-source",
            title="Synthetic failed source",
            content_text="Synthetic test content.",
            source_type="other",
            permission_status="public",
            processing_status="failed",
            source_metadata={
                "ingestion_failed_stage": "event_extraction",
                "ingestion_error": "private-token / local/path must not be exposed",
            },
        )
        db.add(source)
        db.commit()
        company_id, source_id = company.id, source.id

    listing = client.get(f"/api/companies/{company_id}/sources")
    assert listing.status_code == 200
    record = next(item for item in listing.json() if item["id"] == source_id)
    assert record["processing_failed_stage"] == "event_extraction"
    assert "extraction failed" in record["processing_error"].lower()
    assert "private-token" not in record["processing_error"]
    assert "/local/path" not in record["processing_error"]

    detail = client.get(f"/api/companies/{company_id}/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["processing_error"] == record["processing_error"]


def test_feedback_metadata_and_company_scoping_survive_api_round_trip(dashboard_client):
    client, factory = dashboard_client
    source_date = "2025-04-03T12:00:00Z"
    with factory() as db:
        company = Company(name="[SYNTHETIC] Feedback Company")
        other_company = Company(name="[SYNTHETIC] Other Feedback Company")
        db.add_all([company, other_company])
        db.flush()
        public_source = SourceDocument(
            company_id=company.id,
            url="https://example.test/synthetic-public-review",
            title="Synthetic public review source",
            content_text="Synthetic review provenance.",
            source_type="app_review",
            permission_status="public",
        )
        private_source = SourceDocument(
            company_id=company.id,
            url="internal://synthetic-private-feedback",
            title="Synthetic authorized source",
            content_text="Synthetic private provenance.",
            source_type="internal_document",
            permission_status="authorized_internal",
        )
        other_source = SourceDocument(
            company_id=other_company.id,
            url="https://example.test/other-company-review",
            title="Other company source",
            content_text="Other company provenance.",
            source_type="app_review",
            permission_status="public",
        )
        db.add_all([public_source, private_source, other_source])
        db.flush()
        private_feedback = Feedback(
            company_id=company.id,
            source_id=private_source.id,
            feedback_text="[SYNTHETIC] Must remain private.",
            sentiment="negative",
            feedback_type="complaint",
        )
        db.add(private_feedback)
        db.commit()
        company_id = company.id
        other_company_id = other_company.id
        public_source_id = public_source.id
        private_source_id = private_source.id
        other_source_id = other_source.id
        public_source_url = public_source.url

    submitted = client.post("/api/feedback", json={
        "company_id": company_id,
        "source_id": public_source_id,
        "source_url": public_source_url,
        "external_reference": "[SYNTHETIC] review-001",
        "language": "en",
        "created_at_source": source_date,
        "text": "[SYNTHETIC] The setup was clear and helpful.",
        "product_name": "Synthetic Desk Hub",
        "rating": 4.5,
    })
    assert submitted.status_code == 201, submitted.text
    feedback_id = submitted.json()["id"]

    with factory() as db:
        record = db.get(Feedback, feedback_id)
        assert record.company_id == company_id
        assert record.source_id == public_source_id
        assert record.source_url == public_source_url
        assert record.external_reference == "[SYNTHETIC] review-001"
        assert record.language == "en"
        assert record.created_at_source.replace(tzinfo=timezone.utc) == datetime.fromisoformat(source_date.replace("Z", "+00:00"))
        db.execute(feedback_topics.insert().values(feedback_id=feedback_id, topic="second synthetic topic"))
        other_feedback = Feedback(
            company_id=other_company_id,
            source_id=other_source_id,
            feedback_text="[SYNTHETIC] Other company feedback.",
            sentiment="neutral",
            feedback_type="other",
        )
        db.add(other_feedback)
        db.commit()

    listing = client.get(f"/api/companies/{company_id}/feedback")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == feedback_id
    assert item["source_id"] == public_source_id
    assert item["external_reference"] == "[SYNTHETIC] review-001"
    assert item["language"] == "en"
    assert item["created_at_source"].startswith("2025-04-03T12:00:00")
    assert "second synthetic topic" in item["topics"]
    assert "Must remain private" not in str(payload)

    analysis = client.get(f"/api/feedback/analysis/{company_id}").json()
    assert analysis["total_feedback"] == 1
    assert analysis["topic_distribution"]["second synthetic topic"] == 1

    trends = client.get(f"/api/feedback/trends/{company_id}").json()
    assert trends["total_feedback"] == 1
    evidence = next(
        entry
        for trend in trends["trends"]
        for entry in trend["evidence"]
        if entry["feedback_id"] == feedback_id
    )
    assert evidence["product_name"] == "Synthetic Desk Hub"
    assert evidence["created_at_source"].startswith("2025-04-03T12:00:00")
    assert evidence["feedback_type"]

    assert client.get(f"/api/companies/{other_company_id}/feedback").json()["total"] == 1
    assert client.post("/api/feedback", json={
        "company_id": company_id,
        "source_id": other_source_id,
        "text": "[SYNTHETIC] cross-company source must be rejected",
    }).status_code == 400
    assert client.post("/api/feedback", json={
        "company_id": company_id,
        "source_id": private_source_id,
        "text": "[SYNTHETIC] private source must be rejected",
    }).status_code == 400


def test_ingestion_status_filters_internal_records_unless_trusted_local_opt_in(
    dashboard_client,
    monkeypatch,
):
    client, factory = dashboard_client
    with factory() as db:
        company = Company(name="[SYNTHETIC] Ingestion Status Company")
        db.add(company)
        db.flush()
        public_source = SourceDocument(
            company_id=company.id,
            url="https://example.test/synthetic-public-source",
            title="[SYNTHETIC] Public source",
            content_text="[SYNTHETIC] Public evidence excerpt.",
            source_type="company_page",
            permission_status="public",
            processing_status="processed",
        )
        internal_source = SourceDocument(
            company_id=company.id,
            url="local://synthetic-internal-source",
            title="[SYNTHETIC] Authorized internal source",
            content_text="[SYNTHETIC] Internal evidence excerpt.",
            source_type="internal_document",
            permission_status="authorized_internal",
            processing_status="processed",
        )
        db.add_all([public_source, internal_source])
        db.flush()

        public_event = ProductEvent(
            company_id=company.id,
            event_type="product_update",
            title="[SYNTHETIC] Publicly documented update",
            evidence_classification="documented",
        )
        internal_event = ProductEvent(
            company_id=company.id,
            event_type="product_decision",
            title="[SYNTHETIC] Internal-only event",
            evidence_classification="documented",
        )
        mixed_event = ProductEvent(
            company_id=company.id,
            event_type="product_update",
            title="[SYNTHETIC] Mixed-permission event",
            evidence_classification="documented",
        )
        db.add_all([public_event, internal_event, mixed_event])
        db.flush()
        db.execute(event_sources.insert(), [
            {"event_id": public_event.id, "source_id": public_source.id},
            {"event_id": internal_event.id, "source_id": internal_source.id},
            {"event_id": mixed_event.id, "source_id": public_source.id},
            {"event_id": mixed_event.id, "source_id": internal_source.id},
        ])
        db.add_all([
            KnowledgeItem(
                company_id=company.id,
                source_id=public_source.id,
                item_type="decision",
                title="[SYNTHETIC] Public knowledge item",
                description="[SYNTHETIC] Public description.",
                evidence_quote="[SYNTHETIC] Public evidence excerpt.",
                evidence_classification="documented",
            ),
            KnowledgeItem(
                company_id=company.id,
                source_id=internal_source.id,
                item_type="decision",
                title="[SYNTHETIC] Internal knowledge item",
                description="[SYNTHETIC] Internal description.",
                evidence_quote="[SYNTHETIC] Internal evidence excerpt.",
                evidence_classification="documented",
            ),
        ])
        db.commit()
        company_id = company.id

    monkeypatch.delenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", raising=False)
    public = client.get(f"/api/ingestion/companies/{company_id}/status")
    assert public.status_code == 200
    assert public.json()["total_sources"] == 1
    assert public.json()["total_events"] == 1
    assert public.json()["total_knowledge_items"] == 1
    assert public.json()["processing_status_counts"] == {"processed": 1}
    assert client.get(
        f"/api/ingestion/companies/{company_id}/status?include_authorized_internal=true"
    ).status_code == 403

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", "1")
    with TestClient(app, client=("127.0.0.1", 50001)) as trusted_client:
        trusted = trusted_client.get(
            f"/api/ingestion/companies/{company_id}/status?include_authorized_internal=true"
        )
    assert trusted.status_code == 200
    assert trusted.json()["total_sources"] == 2
    assert trusted.json()["total_events"] == 3
    assert trusted.json()["total_knowledge_items"] == 2
    assert trusted.json()["processing_status_counts"] == {"processed": 2}
