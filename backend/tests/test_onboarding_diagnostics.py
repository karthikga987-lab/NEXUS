from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Company, ResearchRun
from app.research import onboarding


def test_onboarding_persists_timed_stage_and_safe_failure_diagnostics(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'onboarding_diagnostics.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with factory() as db:
            company = Company(
                name="[SYNTHETIC] onboarding diagnostics fixture",
                website="https://diagnostics.example",
            )
            db.add(company)
            db.commit()
            company_id = company.id

        def fail_research(**_kwargs):
            raise RuntimeError(
                "Provider failed with token=synthetic-secret at http://127.0.0.1:11434"
            )

        monkeypatch.setattr(onboarding, "collect_company_sources", fail_research)
        monkeypatch.setattr(
            onboarding,
            "process_company_sources",
            lambda **_kwargs: {"counts": {}, "documents_considered": 0, "results": []},
        )
        monkeypatch.setattr(
            onboarding,
            "extract_and_persist_relationships",
            lambda **_kwargs: {
                "relationships_created": 0,
                "provenance_records_created": 0,
                "errors": [],
            },
        )

        onboarding.run_company_onboarding(company_id, factory)

        with factory() as db:
            run = db.query(ResearchRun).filter_by(company_id=company_id).one()
            research_detail = run.counts["workflow_stage_details"]["research"]
            assert research_detail["status"] == "failed"
            assert research_detail["started_at"]
            assert research_detail["completed_at"]
            assert research_detail["duration_ms"] >= 0
            assert research_detail["exception_class"] == "RuntimeError"
            diagnostic = run.counts["diagnostics"][0]
            assert diagnostic["stage"] == "research"
            assert diagnostic["exception_class"] == "RuntimeError"
            assert "synthetic-secret" not in diagnostic["message"]
            assert "127.0.0.1" not in diagnostic["message"]
            assert "[redacted]" in diagnostic["message"]
            assert "[internal address]" in diagnostic["message"]
            assert "RuntimeError" in run.failure_summary
    finally:
        engine.dispose()
