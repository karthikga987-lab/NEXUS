from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.intelligence.knowledge_retrieval import append_relevant_knowledge_item_passages
from app.models import Company, KnowledgeItem, SourceDocument


def test_rag_augments_only_exact_relevant_knowledge_quotes_from_retrieved_sources(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge_retrieval.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        company = Company(name="[SYNTHETIC] Northstar", website="https://northstar.example")
        db.add(company)
        db.flush()
        source = SourceDocument(
            company_id=company.id,
            url="https://northstar.example/product",
            title="Synthetic Northstar product memo",
            content_text="Synthetic Northstar proposed a checkout pilot in May. A review is pending.",
            permission_status="public",
            source_type="company_page",
            source_metadata={"evidence_origin": "public_company"},
        )
        unrelated_source = SourceDocument(
            company_id=company.id,
            url="https://northstar.example/unrelated",
            title="Synthetic unrelated memo",
            content_text="Synthetic Northstar discussed battery recycling.",
            permission_status="public",
            source_type="company_page",
        )
        db.add_all([source, unrelated_source])
        db.flush()
        quote = "Synthetic Northstar proposed a checkout pilot in May."
        db.add_all([
            KnowledgeItem(
                company_id=company.id,
                source_id=source.id,
                item_type="proposal",
                title="Checkout pilot proposal",
                description="The company proposed a checkout pilot.",
                subject_name="Checkout",
                status="proposed",
                evidence_quote=quote,
                evidence_classification="documented",
                extraction_confidence=0.9,
            ),
            KnowledgeItem(
                company_id=company.id,
                source_id=unrelated_source.id,
                item_type="decision",
                title="Battery recycling decision",
                description="An unrelated decision.",
                status="unknown",
                evidence_quote="Synthetic Northstar discussed battery recycling.",
                evidence_classification="documented",
                extraction_confidence=0.8,
            ),
            KnowledgeItem(
                company_id=company.id,
                source_id=source.id,
                item_type="outcome",
                title="Invalid synthetic quote",
                description="This quote is intentionally not in source content.",
                status="unknown",
                evidence_quote="A fabricated statement absent from the source.",
                evidence_classification="unknown",
                extraction_confidence=0.2,
            ),
        ])
        db.commit()

        passages = [{
            "source_id": source.id,
            "source_title": source.title,
            "source_url": source.url,
            "chunk_text": "A review is pending.",
            "similarity": 0.94,
            "permission_status": "public",
            "evidence_scope": "public_company",
        }]
        result = append_relevant_knowledge_item_passages(
            db,
            company_id=company.id,
            query="Was a checkout pilot proposed?",
            retrieved_passages=passages,
        )
        assert len(result) == 2
        item_passage = result[1]
        assert item_passage["chunk_text"] == quote
        assert item_passage["knowledge_item_id"]
        assert item_passage["evidence_quote"] == quote
        assert item_passage["evidence_scope"] == "public_company"
        assert all("battery" not in item["chunk_text"].casefold() for item in result)
        assert all("fabricated" not in item["chunk_text"].casefold() for item in result)
    finally:
        db.close()
        engine.dispose()
