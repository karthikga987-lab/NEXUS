from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.intelligence import embeddings, extraction, ingestion
from app.models import Company, DocumentEmbedding, KnowledgeItem, SourceDocument


def test_no_event_is_successful_and_other_source_failures_are_isolated(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'ingestion.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    db = session_factory()
    try:
        company = Company(
            name="Synthetic Acme",
            website="https://acme.example",
        )
        db.add(company)
        db.flush()
        contents = (
            "Synthetic product document with no completed event. " * 30
        )
        failed_source = SourceDocument(
            company_id=company.id,
            url="https://acme.example/failed",
            title="Synthetic source expected to fail extraction",
            content_text=contents,
            permission_status="public",
            source_type="official_blog",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        successful_source = SourceDocument(
            company_id=company.id,
            url="https://acme.example/no-event",
            title="Synthetic source with no documented event",
            content_text=contents,
            permission_status="public",
            source_type="official_blog",
            collected_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        db.add_all([failed_source, successful_source])
        db.commit()

        monkeypatch.setattr(
            embeddings,
            "generate_embeddings",
            lambda chunks: [[0.01] * 768 for _ in chunks],
        )

        def extract_for_source(source_text, source_id, company_id):
            if source_id == failed_source.id:
                raise extraction.ExtractionError(
                    "Synthetic malformed model response"
                )
            return []

        monkeypatch.setattr(ingestion, "extract_events", extract_for_source)

        result = ingestion.process_company_sources(
            db,
            company.id,
            source_ids=[failed_source.id, successful_source.id],
        )

        assert result["documents_considered"] == 2
        assert result["counts"]["failed"] == 1
        assert result["counts"]["processed"] == 1
        assert result["counts"]["events_extracted"] == 0
        persisted_chunks = db.query(DocumentEmbedding).count()
        assert persisted_chunks == 4
        assert result["counts"]["embedding_chunks_created"] == persisted_chunks

        by_id = {item["source_id"]: item for item in result["results"]}
        assert by_id[failed_source.id]["status"] == "failed"
        assert by_id[successful_source.id]["status"] == "processed"
        assert by_id[successful_source.id]["events_extracted"] == 0
        assert db.get(SourceDocument, successful_source.id).processing_status == "processed"
        failed_after = db.get(SourceDocument, failed_source.id)
        assert failed_after.processing_status == "failed"
        assert failed_after.source_metadata["embedding_chunks_created"] == 2
        assert failed_after.source_metadata["embedding_model"] == embeddings.EMBEDDING_MODEL
    finally:
        db.close()
        engine.dispose()


class _ExtractionWithKnowledge(list):
    def __init__(self, events, knowledge_items):
        super().__init__(events)
        self.knowledge_items = knowledge_items


def test_authorized_internal_ingestion_persists_exact_knowledge_and_embeddings(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'internal_ingestion.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        company = Company(name="[SYNTHETIC] Northstar", website="https://northstar.example")
        db.add(company)
        db.flush()
        quote = "[SYNTHETIC DEMO] The team proposed a checkout pilot."
        source = SourceDocument(
            company_id=company.id,
            url=f"internal://{company.id}/notes.md",
            title="[SYNTHETIC DEMO] notes.md",
            source_type="internal_document",
            content_text=quote + " The outcome is not documented.",
            content_hash="synthetic-internal-hash",
            permission_status="authorized_internal",
            processing_status="pending",
            source_metadata={
                "content_kind": "internal_document",
                "evidence_origin": "synthetic_demo",
                "is_synthetic": True,
            },
        )
        db.add(source)
        db.commit()
        monkeypatch.setattr(
            embeddings,
            "generate_embeddings",
            lambda chunks: [[0.02] * 768 for _ in chunks],
        )
        monkeypatch.setattr(
            ingestion,
            "extract_events",
            lambda **kwargs: _ExtractionWithKnowledge([], [{
                "company_id": company.id,
                "source_id": source.id,
                "item_type": "proposal",
                "title": "Checkout pilot proposal",
                "description": "The team proposed a checkout pilot.",
                "subject_name": "Checkout",
                "actor": "The team",
                "status": "proposed",
                "item_date": None,
                "evidence_quote": quote,
                "evidence_classification": "documented",
                "extraction_confidence": 0.9,
            }]),
        )
        result = ingestion.process_company_sources(
            db,
            company.id,
            source_ids=[source.id],
            include_authorized_internal=True,
        )
        assert result["counts"]["processed"] == 1
        assert result["counts"]["new_knowledge_items"] == 1
        stored = db.query(KnowledgeItem).one()
        assert stored.source_id == source.id
        assert stored.evidence_quote == quote
        assert db.query(DocumentEmbedding).filter_by(source_id=source.id).count() > 0
    finally:
        db.close()
        engine.dispose()
