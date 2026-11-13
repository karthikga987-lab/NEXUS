"""Bounded, in-process company onboarding for the local NEXUS application."""

import logging
import re
import time
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

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)"
    r"(\s*[:=]\s*)[^\s&,;]+"
)
_SECRET_QUERY_PARAMETER = re.compile(
    r"(?i)([?&](?:api_?key|access_?token|token|password|secret)=)"
    r"[^&\s]+"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")
_PRIVATE_ADDRESS = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|127(?:\.\d{1,3}){3}|"
    r"169\.254(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)

_active_companies: set[str] = set()
_active_lock = Lock()


def _safe_diagnostic_message(value: object) -> str:
    """Bound diagnostics and redact common credentials and local addresses."""
    message = " ".join(str(value or "").split())
    message = _SECRET_ASSIGNMENT.sub(r"\1\2[redacted]", message)
    message = _SECRET_QUERY_PARAMETER.sub(r"\1[redacted]", message)
    message = _URL_CREDENTIALS.sub(r"\1[redacted]@", message)
    message = _PRIVATE_ADDRESS.sub("[internal address]", message)
    message = re.sub(r"(?i)\b(?:localhost|127\.0\.0\.1|::1)(?=[:/\s]|$)", "[local service]", message)
    return (message or "No diagnostic message was provided.")[:240]


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
    """Run bounded public research, ingestion, and relationship extraction.

    Each stage records its status in the existing ResearchRun JSON counts.
    A failed stage does not roll back records committed by earlier stages or
    prevent the remaining safe stages from running.
    """
    db = session_factory()
    workflow_stages = {
        "research": "running",
        "ingestion": "queued",
        "knowledge_graph": "queued",
    }
    workflow_stage_details: dict[str, dict] = {}
    stage_errors: list[str] = []
    diagnostics: list[dict] = []
    stage_started_at: dict[str, datetime] = {}
    stage_started_clock: dict[str, float] = {}
    active_stage = "initialization"

    def start_stage(stage: str) -> dict:
        if stage not in stage_started_at:
            stage_started_at[stage] = datetime.now(timezone.utc)
            stage_started_clock[stage] = time.perf_counter()
        detail = dict(workflow_stage_details.get(stage) or {})
        detail.update({
            "status": "running",
            "started_at": detail.get("started_at")
            or stage_started_at[stage].isoformat(),
            "completed_at": None,
            "duration_ms": None,
        })
        workflow_stage_details[stage] = detail
        return detail

    def record_diagnostic(
        stage: str,
        message: object,
        exception_class: str | None = None,
        kind: str = "stage_failure",
    ) -> None:
        diagnostic = {
            "stage": stage,
            "kind": kind,
            "exception_class": exception_class,
            "message": _safe_diagnostic_message(message),
        }
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)

    def latest_run() -> ResearchRun | None:
        return (
            db.query(ResearchRun)
            .filter(ResearchRun.company_id == company_id)
            .order_by(ResearchRun.started_at.desc())
            .first()
        )

    def persist_stage(
        stage: str,
        status: str,
        extra_counts: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        workflow_stages[stage] = status
        if status == "running":
            start_stage(stage)
        else:
            detail = start_stage(stage)
            now = datetime.now(timezone.utc)
            detail["status"] = status
            detail["completed_at"] = now.isoformat()
            detail["duration_ms"] = round(
                (time.perf_counter() - stage_started_clock[stage]) * 1000,
                1,
            )
            if error is not None:
                exception_class = type(error).__name__
                message = _safe_diagnostic_message(error)
                detail["exception_class"] = exception_class
                detail["diagnostic"] = message
                record_diagnostic(
                    stage,
                    message,
                    exception_class=exception_class,
                )
        run = latest_run()
        if run is None:
            run = ResearchRun(
                company_id=company_id,
                status="running",
                started_at=datetime.now(timezone.utc),
                counts={},
            )
            db.add(run)
            db.flush()
        counts = dict(run.counts or {})
        counts.update(extra_counts or {})
        counts["workflow_stages"] = dict(workflow_stages)
        counts["workflow_stage_details"] = {
            key: dict(value) for key, value in workflow_stage_details.items()
        }
        if diagnostics:
            counts["diagnostics"] = list(diagnostics)
        run.counts = counts
        run.status = "running"
        run.completed_at = None
        db.commit()

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
        start_stage("research")
        onboarding_run = ResearchRun(
            company_id=company_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            counts={
                "workflow_stages": dict(workflow_stages),
                "workflow_stage_details": {
                    key: dict(value)
                    for key, value in workflow_stage_details.items()
                },
            },
        )
        db.add(onboarding_run)
        db.commit()

        research: dict = {"counts": {}, "discovery_errors": []}
        active_stage = "research"
        try:
            research = collect_company_sources(
                db=db,
                company_id=company_id,
                max_pages=MAX_ONBOARDING_PAGES,
                search_depth=ONBOARDING_SEARCH_DEPTH,
                research_run_id=onboarding_run.id,
            )
            research_counts = dict(research.get("counts") or {})
            for message in research.get("discovery_errors") or []:
                kind = (
                    "official_site_fallback"
                    if "homepage unavailable" in str(message).casefold()
                    and "search discovery was attempted" in str(message).casefold()
                    else "discovery_failure"
                )
                record_diagnostic("research", message, kind=kind)
            for result in research.get("results") or []:
                if isinstance(result, dict) and result.get("status") == "failed":
                    record_diagnostic(
                        "research",
                        result.get("reason") or "A discovered source could not be collected.",
                        kind="source_collection_failure",
                    )
            research_failed = bool(
                research_counts.get("failed", 0)
                or research.get("discovery_errors")
            )
            persist_stage(
                "research",
                "partial" if research_failed else "completed",
                research_counts,
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Public research failed for company %s", company_id)
            research = {
                "counts": {"failed": 1},
                "discovery_errors": ["Public source discovery or collection failed."],
            }
            research_counts = dict(research["counts"])
            stage_errors.append("research")
            persist_stage("research", "failed", research_counts, error=exc)

        active_stage = "ingestion"
        persist_stage("ingestion", "running")
        ingestion: dict = {"counts": {}, "documents_considered": 0}
        try:
            ingestion = process_company_sources(
                db=db,
                company_id=company_id,
                limit=MAX_INGESTION_SOURCES,
            )
            ingestion_counts = dict(ingestion.get("counts") or {})
            for result in ingestion.get("results") or []:
                if isinstance(result, dict) and result.get("status") == "failed":
                    record_diagnostic(
                        "ingestion",
                        result.get("error") or "A source failed during ingestion.",
                        kind="source_ingestion_failure",
                    )
            ingestion_failed = bool(ingestion_counts.get("failed", 0))
            if ingestion_failed:
                stage_errors.append("ingestion")
            persist_stage(
                "ingestion",
                "partial" if ingestion_failed else "completed",
                {
                    **{f"ingestion_{key}": value for key, value in ingestion_counts.items()},
                    "ingestion_documents_considered": ingestion.get(
                        "documents_considered", 0
                    ),
                },
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Document ingestion failed for company %s", company_id)
            ingestion = {"counts": {"failed": 1}, "documents_considered": 0}
            ingestion_counts = dict(ingestion["counts"])
            stage_errors.append("ingestion")
            persist_stage(
                "ingestion",
                "failed",
                {"ingestion_failed": 1, "ingestion_documents_considered": 0},
                error=exc,
            )

        active_stage = "knowledge_graph"
        persist_stage("knowledge_graph", "running")
        relationships: dict = {"relationships_created": 0, "errors": []}
        try:
            relationships = extract_and_persist_relationships(
                db=db,
                company_id=company_id,
            )
            for message in relationships.get("errors") or []:
                record_diagnostic("knowledge_graph", message, kind="relationship_failure")
            if relationships.get("errors"):
                stage_errors.append("knowledge_graph")
            persist_stage(
                "knowledge_graph",
                "partial" if relationships.get("errors") else "completed",
                {
                    "ingestion_relationships_created": relationships.get(
                        "relationships_created", 0
                    ),
                    "ingestion_relationship_provenance_created": relationships.get(
                        "provenance_records_created", 0
                    ),
                },
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Knowledge graph relationship update failed for company %s", company_id)
            relationships = {"relationships_created": 0, "errors": ["Relationship extraction failed."]}
            stage_errors.append("knowledge_graph")
            persist_stage("knowledge_graph", "failed", error=exc)

        run = latest_run()
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
        research_counts["workflow_stages"] = dict(workflow_stages)
        research_counts["workflow_stage_details"] = {
            key: dict(value) for key, value in workflow_stage_details.items()
        }
        if diagnostics:
            research_counts["diagnostics"] = list(diagnostics)

        research_errors = bool(
            stage_errors
            or research_counts.get("failed", 0)
            or research.get("discovery_errors")
            or ingestion_counts.get("failed", 0)
            or relationships.get("errors")
        )
        if run is not None:
            run.counts = research_counts
            run.status = "completed_with_errors" if research_errors else "completed"
            run.completed_at = datetime.now(timezone.utc)
            if research_errors:
                priority = {
                    "stage_failure": 0,
                    "source_ingestion_failure": 1,
                    "source_collection_failure": 2,
                    "relationship_failure": 3,
                    "discovery_failure": 4,
                    "official_site_fallback": 5,
                }
                first = min(
                    diagnostics,
                    key=lambda item: priority.get(item.get("kind"), 10),
                    default=None,
                )
                if first:
                    exception = (
                        f" ({first['exception_class']})"
                        if first.get("exception_class")
                        else ""
                    )
                    run.failure_summary = (
                        f"{first['stage']}{exception}: {first['message']}"
                    )[:500]
                else:
                    run.failure_summary = (
                        "Some research, ingestion, or relationship stages did not complete."
                    )
            else:
                run.failure_summary = None

        company = db.get(Company, company_id)
        if company is not None:
            company.research_status = "partial" if research_errors else "completed"
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Automatic onboarding failed for company %s", company_id)
        now = datetime.now(timezone.utc)
        detail = dict(workflow_stage_details.get(active_stage) or {})
        started = stage_started_at.get(active_stage, now)
        started_clock = stage_started_clock.get(active_stage)
        message = _safe_diagnostic_message(exc)
        exception_class = type(exc).__name__
        detail.update({
            "status": "failed",
            "started_at": detail.get("started_at") or started.isoformat(),
            "completed_at": now.isoformat(),
            "duration_ms": round((time.perf_counter() - started_clock) * 1000, 1)
            if started_clock is not None else 0.0,
            "exception_class": exception_class,
            "diagnostic": message,
        })
        workflow_stage_details[active_stage] = detail
        workflow_stages[active_stage] = "failed"
        record_diagnostic(active_stage, message, exception_class=exception_class)
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
                counts = dict(run.counts or {})
                counts["workflow_stages"] = dict(workflow_stages)
                counts["workflow_stage_details"] = {
                    key: dict(value) for key, value in workflow_stage_details.items()
                }
                counts["diagnostics"] = list(diagnostics)
                run.counts = counts
                run.failure_summary = (
                    f"{active_stage} ({exception_class}): {message}"
                )[:500]
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist onboarding failure status for company %s", company_id)
    finally:
        db.close()
        _release_onboarding(company_id)
