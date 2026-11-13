import json

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models import Company, DocumentEmbedding, ProductEvent, Proposal, ResearchRun, SourceDocument
from app.models.entities import ProposalAnalysis
from app.schemas.contracts import ProposalAnalyzeIn, ProposalCreateIn
from app.api.routes import companies as companies_route
from app.api.routes import proposals as proposals_route
from app.intelligence import embeddings, ingestion
from app.research import service as research_service
from app.research import onboarding


def _temporary_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'proposal_refresh.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, factory


def test_background_research_uses_request_database_and_existing_worker(
    tmp_path, monkeypatch
):
    engine, factory = _temporary_database(tmp_path)
    try:
        with factory() as db:
            company = Company(
                name="[SYNTHETIC] Proposal refresh company",
                website="https://refresh.example",
            )
            db.add(company)
            db.commit()
            company_id = company.id

            background_tasks = BackgroundTasks()
            response = companies_route.start_research(
                company_id=company_id,
                background_tasks=background_tasks,
                max_pages=6,
                search_depth=3,
                background=True,
                db=db,
            )

            assert response.status_code == 202
            response_body = json.loads(response.body)
            assert response_body["status"] == "queued"
            assert response_body["already_running"] is False
            assert len(background_tasks.tasks) == 1
            scheduled = background_tasks.tasks[0]
            assert scheduled.func is onboarding.run_company_onboarding
            assert scheduled.args[0] == company_id
            worker_factory = scheduled.args[1]
            worker_db = worker_factory()
            assert str(worker_db.get_bind().url) == str(engine.url)
            assert db.get(Company, company_id).research_status == "queued"

            worker_db.close()
            onboarding._release_onboarding(company_id)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_research_failure_does_not_skip_ingestion_or_erase_saved_sources(
    tmp_path, monkeypatch
):
    engine, factory = _temporary_database(tmp_path)
    try:
        with factory() as db:
            company = Company(
                name="[SYNTHETIC] Partial refresh company",
                website="https://partial.example",
            )
            db.add(company)
            db.flush()
            source = SourceDocument(
                company_id=company.id,
                url="https://partial.example/saved",
                title="[SYNTHETIC] Existing source",
                content_text="Synthetic persisted source body.",
                permission_status="public",
                processing_status="pending",
                source_type="other",
            )
            db.add(source)
            db.commit()
            company_id = company.id
            source_id = source.id
            expected_company_id = company.id

        calls = []

        def failed_research(**_kwargs):
            calls.append("research")
            raise RuntimeError("synthetic network failure")

        def process_existing(db, company_id, limit):
            calls.append("ingestion")
            assert db.get(SourceDocument, source_id) is not None
            assert company_id == expected_company_id
            return {
                "status": "completed",
                "documents_considered": 1,
                "counts": {"processed": 1, "failed": 0, "skipped": 0},
            }

        def update_graph(**_kwargs):
            calls.append("knowledge_graph")
            return {"relationships_created": 0, "provenance_records_created": 0, "errors": []}

        monkeypatch.setattr(onboarding, "collect_company_sources", failed_research)
        monkeypatch.setattr(onboarding, "process_company_sources", process_existing)
        monkeypatch.setattr(onboarding, "extract_and_persist_relationships", update_graph)

        onboarding.run_company_onboarding(company_id, factory)

        assert calls == ["research", "ingestion", "knowledge_graph"]
        with factory() as db:
            saved_company = db.get(Company, company_id)
            saved_source = db.get(SourceDocument, source_id)
            run = (
                db.query(ResearchRun)
                .filter(ResearchRun.company_id == company_id)
                .order_by(ResearchRun.started_at.desc())
                .first()
            )
            assert saved_company.research_status == "partial"
            assert saved_source is not None
            assert run.status == "completed_with_errors"
            assert run.counts["workflow_stages"] == {
                "research": "failed",
                "ingestion": "completed",
                "knowledge_graph": "completed",
            }
            assert run.counts["ingestion_processed"] == 1
            assert db.query(ResearchRun).filter_by(company_id=company_id).count() == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_proposal_is_saved_before_refresh_and_analysis_reuses_its_id(
    tmp_path, monkeypatch
):
    engine, factory = _temporary_database(tmp_path)
    try:
        with factory() as db:
            company = Company(
                name="[SYNTHETIC] Proposal ownership company",
                website="https://proposal.example",
            )
            db.add(company)
            db.commit()
            company_id = company.id

            created = proposals_route.create_proposal(
                payload=ProposalCreateIn(
                    company_id=company_id,
                    title="[SYNTHETIC] Water bottle proposal",
                    description="A clearly labelled synthetic product proposal.",
                ),
                db=db,
            )
            assert created["status"] == "submitted"
            assert db.query(Proposal).filter_by(company_id=company_id).count() == 1
            assert db.query(ProposalAnalysis).count() == 0

            monkeypatch.setattr(
                proposals_route,
                "search_similar_chunks",
                lambda **_kwargs: [],
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
                    "event_count": 0,
                    "events": [],
                    "interpretation_warning": "Synthetic test graph context.",
                },
            )
            monkeypatch.setattr(
                proposals_route,
                "_get_customer_feedback",
                lambda **_kwargs: [],
            )
            monkeypatch.setattr(
                proposals_route,
                "analyze_proposal_with_evidence",
                lambda **_kwargs: {
                    "status": "completed",
                    "recommendation": "Insufficient evidence; validate assumptions.",
                    "risks": [],
                    "limitations": [],
                    "claims": [],
                    "evidence_sources": [],
                },
            )

            analysis_result = proposals_route.analyze_proposal(
                payload=ProposalAnalyzeIn(
                    company_id=company_id,
                    proposal_id=created["id"],
                    title=created["title"],
                    description=created["description"],
                ),
                db=db,
            )

            assert analysis_result["proposal_id"] == created["id"]
            assert db.query(Proposal).filter_by(company_id=company_id).count() == 1
            assert db.query(ProposalAnalysis).filter_by(
                proposal_id=created["id"]
            ).count() == 1

            other_company = Company(name="[SYNTHETIC] Different company")
            db.add(other_company)
            db.commit()
            try:
                proposals_route.analyze_proposal(
                    payload=ProposalAnalyzeIn(
                        company_id=other_company.id,
                        proposal_id=created["id"],
                        title=created["title"],
                        description=created["description"],
                    ),
                    db=db,
                )
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError("Cross-company proposal analysis must be rejected")
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_http_proposal_workflow_persists_research_ingestion_and_analysis(
    tmp_path, monkeypatch
):
    """Exercise the API workflow on temporary SQLite with labelled fixtures."""
    engine, factory = _temporary_database(tmp_path)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    company_id = None
    quote = (
        "[SYNTHETIC] On 2025-03-10, NEXUS demo announced a documented "
        "product feature update."
    )
    page_text = (quote + " The product feature update describes product features. ") * 30
    html = f"<html><head><title>NEXUS demo product update</title></head><body><main><p>{page_text}</p></main></body></html>"
    source_url = "https://nexus-demo.example/product-updates/synthetic"

    try:
        with factory() as db:
            company = Company(
                name="[SYNTHETIC] NEXUS Demo",
                website="https://nexus-demo.example",
                industry="Synthetic test fixture",
            )
            db.add(company)
            db.commit()
            company_id = company.id

        monkeypatch.setattr(
            research_service,
            "discover_sources",
            lambda **_kwargs: ["https://nexus-demo.example/"],
        )
        monkeypatch.setattr(
            research_service,
            "discover_company_candidates",
            lambda _company, **_kwargs: ([{
                "url": source_url,
                "evidence_origin": "public_company",
                "source_category": "official_blog",
                "discovery_method": "synthetic_test_fixture",
                "original_url": source_url,
            }], []),
        )
        monkeypatch.setattr(
            research_service,
            "fetch_url_with_diagnostics",
            lambda _url: {"content": html, "reason": None},
        )
        monkeypatch.setattr(
            embeddings,
            "generate_embeddings",
            lambda texts: [[1.0] + [0.0] * 767 for _ in texts],
        )

        def synthetic_event_extraction(source_text, source_id, company_id):
            assert quote in source_text
            return [{
                "company_id": company_id,
                "source_id": source_id,
                "product_name": "NEXUS Demo Product",
                "event_type": "feature_change",
                "title": "[SYNTHETIC] Documented demo feature update",
                "description": "A synthetic fixture event used only for workflow testing.",
                "event_date": "2025-03-10",
                "stated_reason": None,
                "outcome_summary": None,
                "evidence_status": "documented",
                "extraction_confidence": 0.95,
                "evidence_quote": quote,
            }]

        monkeypatch.setattr(ingestion, "extract_events", synthetic_event_extraction)
        monkeypatch.setattr(
            proposals_route,
            "search_external_public_chunks",
            lambda **_kwargs: [],
        )

        def synthetic_proposal_analysis(**kwargs):
            source_id = kwargs["evidence_chunks"][0]["source_id"]
            return {
                "status": "completed",
                "recommendation": "PILOT only after validating synthetic assumptions.",
                "risks": ["Synthetic evaluation does not establish real company outcomes."],
                "limitations": [],
                "claims": [{
                    "statement": "The synthetic source documents the demo feature update.",
                    "type": "factual_observation",
                    "source_ids": [source_id],
                }],
                "evidence_sources": [{
                    "source_id": source_id,
                    "evidence_scope": "public_company",
                }],
            }

        monkeypatch.setattr(
            proposals_route,
            "analyze_proposal_with_evidence",
            synthetic_proposal_analysis,
        )

        saved_response = client.post("/api/proposals", json={
            "company_id": company_id,
            "title": "[SYNTHETIC] Test proposal",
            "description": "A clearly labelled synthetic proposal for testing workflow persistence.",
        })
        assert saved_response.status_code == 201
        proposal_id = saved_response.json()["id"]

        research_response = client.post(
            f"/api/companies/{company_id}/research?max_pages=6&search_depth=3&background=true"
        )
        assert research_response.status_code == 202
        assert research_response.json()["status"] == "queued"

        sources_response = client.get(f"/api/companies/{company_id}/sources")
        assert sources_response.status_code == 200
        source = next(item for item in sources_response.json() if item["url"] == source_url)
        source_id = source["id"]
        assert source["processing_status"] == "processed"
        assert quote in str(source.get("extracted_event_evidence"))

        events_response = client.get(f"/api/companies/{company_id}/events")
        assert events_response.status_code == 200
        assert len(events_response.json()) == 1

        with factory() as db:
            assert db.query(DocumentEmbedding).filter_by(source_id=source_id).count() > 0
            assert db.query(ResearchRun).filter_by(company_id=company_id).count() == 1
            event = db.query(ProductEvent).filter_by(company_id=company_id).one()
            assert event.title == "[SYNTHETIC] Documented demo feature update"

        analyze_response = client.post("/api/proposals/analyze", json={
            "company_id": company_id,
            "proposal_id": proposal_id,
            "title": "[SYNTHETIC] Test proposal",
            "description": "A clearly labelled synthetic proposal for testing workflow persistence.",
        })
        assert analyze_response.status_code == 200
        analysis_result = analyze_response.json()
        assert analysis_result["proposal_id"] == proposal_id
        assert analysis_result["status"] == "completed"
        assert analysis_result["evidence"][0]["source_id"] == source_id

        graph_response = client.get(f"/api/companies/{company_id}/knowledge-graph")
        assert graph_response.status_code == 200
        graph = graph_response.json()
        assert any(item.get("proposal_id") == proposal_id for item in graph["nodes"])
        assert graph["summary"]["node_count"] == len(graph["nodes"])
        assert graph["summary"]["edge_count"] == len(graph["edges"])

        feedback_response = client.get(f"/api/companies/{company_id}/feedback")
        assert feedback_response.status_code == 200
        assert feedback_response.json()["total"] == 0
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        Base.metadata.drop_all(engine)
        engine.dispose()
