import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.intelligence import embeddings, ingestion
from app.main import app
from app.models import Company, DocumentEmbedding, KnowledgeItem, SourceDocument


@pytest.fixture
def client_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'internal_sources.db'}")
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
    client = TestClient(app, client=("127.0.0.1", 12345))
    try:
        with factory() as db:
            company = Company(name="[SYNTHETIC TEST] Local", website="https://local.example")
            db.add(company)
            db.commit()
            company_id = company.id
        yield client, factory, company_id
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def test_internal_source_import_is_disabled_by_default(client_db, monkeypatch):
    client, _, company_id = client_db
    monkeypatch.delenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", raising=False)
    response = client.post(
        f"/api/companies/{company_id}/internal-sources",
        files={"file": ("synthetic-notes.txt", b"Synthetic authorized note.", "text/plain")},
    )
    assert response.status_code == 403


def test_local_import_listing_validation_and_company_association(client_db, monkeypatch):
    client, factory, company_id = client_db
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", "1")
    content = b"Synthetic internal notes: the product team proposed a pilot."
    imported = client.post(
        f"/api/companies/{company_id}/internal-sources",
        files={"file": ("team-notes.md", content, "text/markdown")},
        data={"is_synthetic": "true", "author": "Synthetic fixture owner"},
    )
    assert imported.status_code == 201, imported.text
    payload = imported.json()
    assert payload["permission_status"] == "authorized_internal"
    assert payload["is_synthetic"] is True
    assert payload["title"].startswith("[SYNTHETIC DEMO]")

    listing = client.get(f"/api/companies/{company_id}/internal-sources")
    detail = client.get(
        f"/api/companies/{company_id}/internal-sources/{payload['id']}"
    )
    public_sources = client.get(f"/api/companies/{company_id}/sources")
    assert listing.status_code == detail.status_code == public_sources.status_code == 200
    assert len(listing.json()) == 1
    assert detail.json()["content_text"].startswith("[SYNTHETIC DEMO")
    assert public_sources.json() == []

    duplicate = client.post(
        f"/api/companies/{company_id}/internal-sources",
        files={"file": ("team-notes.md", content, "text/markdown")},
        data={"is_synthetic": "true"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == payload["id"]
    assert duplicate.json()["unchanged"] is True

    with factory() as db:
        row = db.get(SourceDocument, payload["id"])
        assert row.company_id == company_id
        assert row.source_metadata["original_filename"] == "team-notes.md"
        assert row.source_metadata["evidence_origin"] == "synthetic_demo"
        assert db.query(SourceDocument).count() == 1


def test_internal_import_rejects_unsupported_oversized_and_non_utf8(client_db, monkeypatch):
    client, factory, company_id = client_db
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", "1")
    cases = [
        ("file.pdf", b"synthetic", 415),
        ("too-large.txt", b"x" * 1_000_001, 413),
        ("bad-encoding.txt", b"\xff\xfe", 400),
    ]
    for filename, content, expected_status in cases:
        response = client.post(
            f"/api/companies/{company_id}/internal-sources",
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert response.status_code == expected_status, response.text
    with factory() as db:
        assert db.query(SourceDocument).count() == 0


def test_internal_ingestion_opt_in_is_guarded(client_db, monkeypatch):
    client, _, company_id = client_db
    monkeypatch.delenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", raising=False)
    response = client.post(
        f"/api/ingestion/companies/{company_id}/process?include_authorized_internal=true",
        json={"source_ids": []},
    )
    assert response.status_code == 403


class _ExtractionWithItems(list):
    def __init__(self, items):
        super().__init__([])
        self.knowledge_items = items


def test_internal_document_runs_through_ingestion_embedding_knowledge_and_rag(
    client_db, monkeypatch
):
    client, factory, company_id = client_db
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", "1")
    source_text = (
        "[SYNTHETIC DEMO] Northstar's team proposed a checkout pilot in May. "
        "No outcome is documented in this labelled fixture."
    )
    imported = client.post(
        f"/api/companies/{company_id}/internal-sources",
        files={"file": ("northstar-notes.md", source_text.encode(), "text/markdown")},
        data={"is_synthetic": "true"},
    )
    assert imported.status_code == 201, imported.text
    source_id = imported.json()["id"]
    quote = "Northstar's team proposed a checkout pilot in May."
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda chunks: [[1.0] + [0.0] * 767 for _ in chunks],
    )
    monkeypatch.setattr(
        ingestion,
        "extract_events",
        lambda **kwargs: _ExtractionWithItems([{
            "company_id": company_id,
            "source_id": source_id,
            "item_type": "proposal",
            "title": "Checkout pilot proposal",
            "description": "The team proposed a checkout pilot.",
            "subject_name": "Checkout",
            "actor": "Northstar's team",
            "status": "proposed",
            "item_date": None,
            "evidence_quote": quote,
            "evidence_classification": "documented",
            "extraction_confidence": 0.9,
        }]),
    )
    processed = client.post(
        f"/api/ingestion/companies/{company_id}/process?include_authorized_internal=true",
        json={"source_ids": [source_id]},
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["counts"]["processed"] == 1
    assert processed.json()["counts"]["new_knowledge_items"] == 1

    items = client.get(
        f"/api/companies/{company_id}/knowledge-items?include_authorized_internal=true"
    )
    assert items.status_code == 200, items.text
    assert len(items.json()) == 1
    assert items.json()[0]["evidence_quote"] == quote
    assert items.json()[0]["evidence_origin"] == "synthetic_demo"
    assert items.json()[0]["is_synthetic"] is True

    search = client.post(
        "/api/ai/search",
        json={
            "company_id": company_id,
            "query": "Northstar checkout pilot",
            "include_authorized_internal": True,
        },
    )
    assert search.status_code == 200, search.text
    assert search.json()["authorized_internal_result_count"] == 1
    assert search.json()["internal_evidence"][0]["evidence_scope"] == "authorized_internal"

    answer = client.post(
        "/api/ai/answer",
        json={
            "company_id": company_id,
            "query": "What checkout pilot did Northstar's team propose?",
            "include_authorized_internal": True,
        },
    )
    assert answer.status_code == 200, answer.text
    assert any(
        source["permission_status"] == "authorized_internal"
        for source in answer.json()["evidence_sources"]
    )
    with factory() as db:
        assert db.query(KnowledgeItem).filter_by(source_id=source_id).count() == 1
        assert db.query(DocumentEmbedding).filter_by(source_id=source_id).count() >= 1
        assert db.get(SourceDocument, source_id).processing_status == "processed"
