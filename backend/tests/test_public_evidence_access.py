from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.ai import SemanticSearchRequest, semantic_search
from app.api.routes.companies import list_events, list_sources
from app.api.routes.proposals import get_proposal_analysis
from app.db.session import Base
from app.intelligence import embeddings
from app.knowledge_graph.builder import build_company_graph
from app.models import (
    Company,
    DocumentEmbedding,
    EventRelationship,
    ProductEvent,
    Proposal,
    SourceDocument,
)
from app.models.entities import (
    AnalysisEvidence,
    ProposalAnalysis,
    event_sources,
    relationship_sources,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'public_access.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_unauthenticated_read_apis_expose_only_public_evidence(db, monkeypatch):
    company = Company(name="[SYNTHETIC TEST] Acme", website="https://acme.example")
    db.add(company)
    db.flush()

    public_source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/public",
        title="Synthetic public source",
        content_text="A public synthetic evidence passage.",
        permission_status="public",
        source_type="press_release",
    )
    internal_source = SourceDocument(
        company_id=company.id,
        url="https://acme.example/internal",
        title="Synthetic internal source",
        content_text="A private synthetic evidence passage.",
        permission_status="authorized_internal",
        source_type="internal_document",
    )
    db.add_all([public_source, internal_source])
    db.flush()

    public_event = ProductEvent(
        company_id=company.id,
        event_type="product_update",
        title="Synthetic public event",
        evidence_classification="documented",
    )
    shared_event = ProductEvent(
        company_id=company.id,
        event_type="product_update",
        title="Synthetic event with public and internal sources",
        evidence_classification="documented",
    )
    internal_event = ProductEvent(
        company_id=company.id,
        event_type="product_update",
        title="Synthetic internal-only event",
        evidence_classification="documented",
    )
    second_public_event = ProductEvent(
        company_id=company.id,
        event_type="product_update",
        title="Second synthetic public event",
        evidence_classification="documented",
    )
    db.add_all([public_event, shared_event, internal_event, second_public_event])
    db.flush()

    db.execute(event_sources.insert(), [
        {"event_id": public_event.id, "source_id": public_source.id},
        {"event_id": shared_event.id, "source_id": public_source.id},
        {"event_id": shared_event.id, "source_id": internal_source.id},
        {"event_id": internal_event.id, "source_id": internal_source.id},
        {"event_id": second_public_event.id, "source_id": public_source.id},
    ])

    public_relationship = EventRelationship(
        company_id=company.id,
        from_event_id=public_event.id,
        to_event_id=second_public_event.id,
        relationship_type="PRECEDED_BY",
        evidence_status="supported_relationship",
        explanation="Synthetic relation supported by a public source.",
        confidence=0.8,
    )
    private_relationship = EventRelationship(
        company_id=company.id,
        from_event_id=public_event.id,
        to_event_id=second_public_event.id,
        relationship_type="MOTIVATED_BY",
        evidence_status="supported_relationship",
        explanation="Synthetic relation supported only by a private source.",
        confidence=0.7,
    )
    db.add_all([public_relationship, private_relationship])
    db.flush()
    db.execute(relationship_sources.insert().values(
        relationship_id=public_relationship.id,
        source_id=public_source.id,
        supporting_quote="A public synthetic evidence passage.",
        verification_method="synthetic_fixture",
        created_at=datetime.now(timezone.utc),
    ))
    db.execute(relationship_sources.insert().values(
        relationship_id=private_relationship.id,
        source_id=internal_source.id,
        supporting_quote="A private synthetic evidence passage.",
        verification_method="synthetic_fixture",
        created_at=datetime.now(timezone.utc),
    ))

    vector = [1.0] + [0.0] * 767
    db.add_all([
        DocumentEmbedding(
            source_id=public_source.id,
            chunk_index=0,
            chunk_text=public_source.content_text,
            embedding=vector,
            model_name=embeddings.EMBEDDING_MODEL,
        ),
        DocumentEmbedding(
            source_id=internal_source.id,
            chunk_index=0,
            chunk_text=internal_source.content_text,
            embedding=vector,
            model_name=embeddings.EMBEDDING_MODEL,
        ),
    ])

    proposal = Proposal(
        company_id=company.id,
        title="Synthetic proposal",
        description="A clearly labelled synthetic proposal for access testing.",
    )
    db.add(proposal)
    db.flush()
    analysis = ProposalAnalysis(
        proposal_id=proposal.id,
        status="completed",
        recommendation="Synthetic recommendation derived from private evidence.",
        risks=[],
        limitations=[],
    )
    db.add(analysis)
    db.flush()
    db.add(AnalysisEvidence(
        analysis_id=analysis.id,
        source_id=internal_source.id,
        claim="Private synthetic claim.",
        evidence_classification="documented",
    ))
    db.commit()

    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: [vector for _ in texts],
    )

    visible_sources = list_sources(company.id, db)
    assert [source.id for source in visible_sources] == [public_source.id]

    visible_events = list_events(company.id, db)
    visible_event_ids = {event["id"] for event in visible_events}
    assert visible_event_ids == {
        public_event.id,
        second_public_event.id,
    }
    assert all(
        source_id == public_source.id
        for event in visible_events
        for source_id in event["source_ids"]
    )

    search = semantic_search(
        SemanticSearchRequest(company_id=company.id, query="synthetic evidence"),
        db,
    )
    assert search["internal_result_count"] == 1
    assert search["internal_evidence"][0]["source_id"] == public_source.id

    graph = build_company_graph(db, company.id)
    graph_source_ids = {
        data["source_id"]
        for _, data in graph.nodes(data=True)
        if data.get("node_type") == "source"
    }
    graph_event_ids = {
        data["event_id"]
        for _, data in graph.nodes(data=True)
        if data.get("node_type") == "event"
    }
    graph_relationship_ids = {
        data["relationship_id"]
        for _, _, data in graph.edges(data=True)
        if data.get("relationship_id")
    }
    assert graph_source_ids == {public_source.id}
    assert graph_event_ids == {
        public_event.id,
        second_public_event.id,
    }
    assert graph_relationship_ids == {public_relationship.id}

    with pytest.raises(HTTPException) as error:
        get_proposal_analysis(analysis.id, db)
    assert error.value.status_code == 404


def test_saved_proposal_analysis_labels_public_company_evidence_correctly(db):
    company = Company(
        name="[SYNTHETIC TEST] Northstar",
        website="https://northstar.example",
    )
    db.add(company)
    db.flush()

    source = SourceDocument(
        company_id=company.id,
        url="https://northstar.example/public-product-page",
        title="Synthetic public product page",
        content_text="Public synthetic source text.",
        permission_status="public",
        source_type="company_page",
    )
    proposal = Proposal(
        company_id=company.id,
        title="[SYNTHETIC] Proposal",
        description="A labelled synthetic proposal.",
    )
    db.add_all([source, proposal])
    db.flush()

    analysis = ProposalAnalysis(
        proposal_id=proposal.id,
        status="completed",
        recommendation="Synthetic recommendation.",
        risks=[],
        limitations=[],
    )
    db.add(analysis)
    db.flush()
    db.add(AnalysisEvidence(
        analysis_id=analysis.id,
        source_id=source.id,
        claim="The public page describes the product.",
        evidence_classification="unknown",
    ))
    db.commit()

    response = get_proposal_analysis(analysis.id, db)

    assert response["claims"][0]["evidence_scope"] == "public_company"
    assert response["claims"][0]["sources"][0]["evidence_scope"] == "public_company"
