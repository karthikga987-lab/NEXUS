"""Bounded, in-process company onboarding for the local NEXUS application."""

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Callable

from sqlalchemy.orm import Session

from app.intelligence.ingestion import process_company_sources
from app.intelligence.relationship_extraction import extract_and_persist_relationships
from app.models import Company, ResearchRun
from app.research.service import collect_company_sources

logger = logging.getLogger(__name__)

MAX_ONBOARDING_PAGES = 6
ONBOARDING_SEARCH_DEPTH = 3
MAX_INGESTION_SOURCES = 25

_active_companies: set[str] = set()
_active_lock = Lock()


def reserve_onboarding(company_id: str) -> bool:
    """Reserve a single in-process job per company."""
    with _active_lock:
        if company_id in _active_companies:
            return False
        _active_companies.add(company_id)
        return True


def _release_onboarding(company_id: str) -> None:
    with _active_lock:
        _active_companies.discard(company_id)


def run_company_onboarding(company_id: str, session_factory: Callable[[], Session]) -> None:
    """Run bounded public research and existing ingestion in a background task.

    The factory is built from the request's SQLAlchemy bind, which keeps this
    worker on the same configured database without relying on global state.
    """
    db = session_factory()
    try:
        company = db.get(Company, company_id)
        if company is None:
            logger.warning("Onboarding skipped because company %s no longer exists", company_id)
            return
        if not company.website:
            company.research_status = "not_started"
            db.commit()
            return

        company.research_status = "running"
        db.commit()

        research = collect_company_sources(
            db=db,
            company_id=company_id,
            max_pages=MAX_ONBOARDING_PAGES,
            search_depth=ONBOARDING_SEARCH_DEPTH,
        )
        ingestion = process_company_sources(
            db=db,
            company_id=company_id,
            limit=MAX_INGESTION_SOURCES,
        )
        relationships = extract_and_persist_relationships(
            db=db,
            company_id=company_id,
        )

        run = (
            db.query(ResearchRun)
            .filter(ResearchRun.company_id == company_id)
            .order_by(ResearchRun.started_at.desc())
            .first()
        )
        research_counts = dict((research.get("counts") or {}))
        ingestion_counts = dict((ingestion.get("counts") or {}))
        research_counts.update({
            f"ingestion_{key}": value for key, value in ingestion_counts.items()
        })
        research_counts["ingestion_documents_considered"] = ingestion.get(
            "documents_considered", 0
        )
        research_counts["ingestion_relationships_created"] = relationships.get(
            "relationships_created", 0
        )
        research_counts["ingestion_relationship_provenance_created"] = relationships.get(
            "provenance_records_created", 0
        )

        research_errors = bool(
            research_counts.get("failed", 0)
            or research.get("discovery_errors")
            or ingestion_counts.get("failed", 0)
            or relationships.get("errors")
        )
        if run is not None:
            run.counts = research_counts
            run.status = "completed_with_errors" if research_errors else "completed"
            run.completed_at = datetime.now(timezone.utc)
            if research_errors:
                run.failure_summary = (
                    "Some discovery, fetch, or document processing steps failed; "
                    "see source and ingestion statuses for details."
                )[:500]

        company.research_status = "partial" if research_errors else "completed"
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Automatic onboarding failed for company %s", company_id)
        try:
            company = db.get(Company, company_id)
            if company is not None:
                company.research_status = "failed"
                run = (
                    db.query(ResearchRun)
                    .filter(ResearchRun.company_id == company_id)
                    .order_by(ResearchRun.started_at.desc())
                    .first()
                )
                if run is None:
                    run = ResearchRun(
                        company_id=company_id,
                        status="failed",
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(run)
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.failure_summary = "Automatic onboarding stopped after a research or ingestion error."
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist onboarding failure status for company %s", company_id)
    finally:
        db.close()
        _release_onboarding(company_id)
