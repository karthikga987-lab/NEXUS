from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models import Company, Proposal, SourceDocument
from app.models.entities import AnalysisEvidence, ProposalAnalysis


@pytest.fixture
def proposal_history_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'proposal_history.db'}")
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
        with factory() as db:
            portronics = Company(name="[SYNTHETIC TEST] Portronics")
            xiaomi = Company(name="[SYNTHETIC TEST] Xiaomi")
            db.add_all([portronics, xiaomi])
            db.flush()

            completed = Proposal(
                company_id=portronics.id,
                title="[SYNTHETIC] Reusable bottle proposal",
                description="A clearly labelled proposal for a reusable bottle.",
                status="submitted",
            )
            submitted = Proposal(
                company_id=portronics.id,
                title="[SYNTHETIC] Unanalyzed packaging proposal",
                description="A submitted proposal with no saved analysis yet.",
                status="submitted",
            )
            xiaomi_proposal = Proposal(
                company_id=xiaomi.id,
                title="[SYNTHETIC] Xiaomi proposal",
                description="A separate company proposal with no cross-link.",
                status="submitted",
            )
            db.add_all([completed, submitted, xiaomi_proposal])
            db.flush()

            source = SourceDocument(
                company_id=portronics.id,
                url="https://portronics.example/synthetic-source",
                title="Synthetic public source",
                content_text="Synthetic source content.",
                permission_status="public",
                source_type="company_page",
            )
            analysis = ProposalAnalysis(
                proposal_id=completed.id,
                status="completed",
                recommendation="Run a small labelled pilot.",
                risks=["Synthetic risk"],
                limitations=["Synthetic limitation"],
                completed_at=datetime.now(timezone.utc),
            )
            restricted_analysis = ProposalAnalysis(
                proposal_id=completed.id,
                status="completed",
                recommendation="Must not be exposed from a public history response.",
                risks=[],
                limitations=[],
                completed_at=datetime.now(timezone.utc),
            )
            internal_source = SourceDocument(
                company_id=portronics.id,
                url="https://portronics.example/synthetic-internal",
                title="Synthetic authorized internal source",
                content_text="Synthetic internal source content.",
                permission_status="authorized_internal",
                source_type="internal_document",
            )
            db.add_all([source, internal_source, analysis, restricted_analysis])
            db.flush()
            db.add_all([
                AnalysisEvidence(
                    analysis_id=analysis.id,
                    source_id=source.id,
                    claim="The synthetic public source supports this claim.",
                    evidence_classification="documented",
                ),
                AnalysisEvidence(
                    analysis_id=restricted_analysis.id,
                    source_id=internal_source.id,
                    claim="Restricted synthetic claim.",
                    evidence_classification="documented",
                ),
            ])
            db.commit()
            ids = {
                "portronics": portronics.id,
                "xiaomi": xiaomi.id,
                "proposal": completed.id,
                "submitted": submitted.id,
                "analysis": analysis.id,
            }

        yield client, ids
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def test_company_proposal_history_is_persistent_and_company_scoped(
    proposal_history_client,
):
    client, ids = proposal_history_client

    response = client.get(f"/api/proposals/company/{ids['portronics']}")
    assert response.status_code == 200
    proposals = response.json()

    assert {item["id"] for item in proposals} == {
        ids["proposal"],
        ids["submitted"],
    }
    saved = next(item for item in proposals if item["id"] == ids["proposal"])
    assert saved["title"] == "[SYNTHETIC] Reusable bottle proposal"
    assert saved["workflow_status"] == "completed"
    assert {item["id"] for item in saved["analyses"]} == {
        ids["analysis"],
        # The other analysis is intentionally restricted but its identifier
        # remains available as a non-openable status entry.
        next(item["id"] for item in saved["analyses"] if not item["accessible"]),
    }
    accessible = next(item for item in saved["analyses"] if item["accessible"])
    assert accessible["recommendation"] == "Run a small labelled pilot."

    submitted = next(item for item in proposals if item["id"] == ids["submitted"])
    assert submitted["workflow_status"] == "submitted"
    assert submitted["analyses"] == []

    xiaomi_response = client.get(f"/api/proposals/company/{ids['xiaomi']}")
    assert xiaomi_response.status_code == 200
    xiaomi_proposals = xiaomi_response.json()
    assert len(xiaomi_proposals) == 1
    assert xiaomi_proposals[0]["company_id"] == ids["xiaomi"]
    assert xiaomi_proposals[0]["title"] == "[SYNTHETIC] Xiaomi proposal"

    detail = client.get(f"/api/proposals/{ids['analysis']}")
    assert detail.status_code == 200
    assert detail.json()["proposal"]["id"] == ids["proposal"]

    graph_response = client.get(
        f"/api/companies/{ids['portronics']}/knowledge-graph"
    )
    assert graph_response.status_code == 200
    graph = graph_response.json()
    proposal_nodes = [
        item for item in graph["nodes"] if item.get("node_type") == "proposal"
    ]
    assert {item["proposal_id"] for item in proposal_nodes} == {
        ids["proposal"],
        ids["submitted"],
    }
    proposal_edges = [
        item for item in graph["edges"]
        if item["source"] == f"proposal:{ids['proposal']}"
    ]
    assert any(item["relation_type"] == "CITES_SOURCE" for item in proposal_edges)
    assert any(item["relation_type"] == "HAS_ANALYSIS" for item in proposal_edges)
    assert any(
        item.get("node_type") == "proposal_analysis"
        and item.get("analysis_id") == ids["analysis"]
        for item in graph["nodes"]
    )
    summary = graph["summary"]
    assert summary["node_counts"]["proposal"] == len(proposal_nodes)
    assert summary["node_counts"]["proposal_analysis"] == sum(
        item.get("node_type") == "proposal_analysis" for item in graph["nodes"]
    )
    assert all(
        item.get("analysis_claim") != "Restricted synthetic claim."
        for item in proposal_edges
    )


def test_company_proposal_history_reports_missing_company(proposal_history_client):
    client, _ = proposal_history_client
    response = client.get("/api/proposals/company/not-a-company")
    assert response.status_code == 404


def test_proposal_can_be_saved_before_analysis(proposal_history_client):
    client, ids = proposal_history_client
    response = client.post("/api/proposals", json={
        "company_id": ids["portronics"],
        "title": "[SYNTHETIC] Proposal saved before refresh",
        "description": "A clearly labelled proposal awaiting company refresh.",
    })
    assert response.status_code == 201
    saved = response.json()
    assert saved["company_id"] == ids["portronics"]
    assert saved["status"] == "submitted"

    history = client.get(f"/api/proposals/company/{ids['portronics']}")
    assert history.status_code == 200
    assert any(item["id"] == saved["id"] and not item["analyses"] for item in history.json())
