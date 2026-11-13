
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Company, Proposal
from app.models.entities import ProposalAnalysis
from app.schemas.contracts import ProposalAnalyzeIn
from app.api.routes import proposals as proposals_route


def test_competitor_rollback_does_not_remove_submitted_proposal(
    tmp_path,
    monkeypatch,
):
    """
    A competitor research failure must not roll back the proposal.

    Uses a real temporary SQLite database and mocks expensive AI/retrieval
    operations so the test does not require Ollama or network access.
    """

    database_path = tmp_path / "proposal_transaction_test.db"

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    main_db = TestSessionLocal()

    try:
        company = Company(
            name="NEXUS Transaction Test",
            website="https://nexus.example",
            industry="Technology",
        )

        main_db.add(company)
        main_db.commit()
        main_db.refresh(company)

        company_id = company.id

        monkeypatch.setattr(
            proposals_route,
            "SessionLocal",
            TestSessionLocal,
        )

        monkeypatch.setattr(
            proposals_route,
            "search_similar_chunks",
            lambda **kwargs: [],
        )

        monkeypatch.setattr(
            proposals_route,
            "search_external_public_chunks",
            lambda **kwargs: [],
        )

        monkeypatch.setattr(
            proposals_route,
            "_build_company_graph_context",
            lambda **kwargs: {
                "company_id": company_id,
                "event_count": 0,
                "events": [],
                "interpretation_warning": (
                    "Test graph context."
                ),
            },
        )

        monkeypatch.setattr(
            proposals_route,
            "_get_customer_feedback",
            lambda **kwargs: [],
        )

        monkeypatch.setattr(
            proposals_route,
            "analyze_proposal_with_evidence",
            lambda **kwargs: {
                "status": "completed",
                "recommendation": "Insufficient evidence.",
                "risks": [],
                "limitations": [],
                "claims": [],
                "evidence_sources": [],
            },
        )

        competitor_observations = {}

        def failing_competitor_research(
            db,
            proposal_company,
            proposal_title,
            proposal_description,
            query_generator=None,
        ):
            # The proposal must already be committed and visible
            # from the independent competitor research session.
            saved_proposal = (
                db.query(Proposal)
                .filter(
                    Proposal.company_id == company_id,
                    Proposal.title == proposal_title,
                )
                .first()
            )

            competitor_observations["proposal_visible"] = (
                saved_proposal is not None
            )

            # Simulate a competitor write followed by a failure.
            db.add(
                Company(
                    name="Temporary Competitor",
                    website="https://temporary-competitor.example",
                    industry="Technology",
                )
            )
            db.flush()

            raise RuntimeError(
                "Simulated competitor research failure"
            )

        monkeypatch.setattr(
            proposals_route,
            "discover_and_ingest_competitors",
            failing_competitor_research,
        )

        payload = ProposalAnalyzeIn(
            company_id=company_id,
            title="AI-powered product recommendation",
            description=(
                "Evaluate an AI-powered recommendation feature "
                "using historical product evidence and feedback."
            ),
            include_fresh_external_research=True,
        )

        response = proposals_route.analyze_proposal(
            payload=payload,
            db=main_db,
        )

        assert competitor_observations["proposal_visible"] is True

        assert response["proposal_id"]
        assert response["analysis_id"]

        # Verify persistence from a completely new session.
        verification_db = TestSessionLocal()

        try:
            saved_proposal = verification_db.get(
                Proposal,
                response["proposal_id"],
            )

            saved_analysis = (
                verification_db.query(ProposalAnalysis)
                .filter(
                    ProposalAnalysis.id == response["analysis_id"]
                )
                .first()
            )

            assert saved_proposal is not None
            assert saved_proposal.status == "submitted"

            assert saved_analysis is not None
            assert (
                saved_analysis.proposal_id
                == saved_proposal.id
            )

            assert (
                response["external_research"]["status"]
                == "failed"
            )

        finally:
            verification_db.close()

    finally:
        main_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
