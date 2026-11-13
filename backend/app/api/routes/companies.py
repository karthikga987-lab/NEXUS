from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.models import Company, ResearchRun, SourceDocument, ProductEvent
from app.models.entities import event_sources
from app.schemas.contracts import (
    CompanyCreate,
    CompanyOut,
    SourceOut,
    EventOut,
)
from app.research.service import collect_company_sources
from app.research.discovery import SourceDiscoveryError
from app.research.onboarding import run_company_onboarding, reserve_onboarding
from app.research.status import effective_research_status


router = APIRouter()


def _company_response(company: Company, latest_run_status: str | None = None) -> dict:
    return {
        "id": company.id,
        "name": company.name,
        "website": company.website,
        "industry": company.industry,
        "description": company.description,
        "research_status": effective_research_status(
            company.research_status,
            latest_run_status,
        ),
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(
    payload: CompanyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    company = Company(**payload.model_dump())
    if company.website:
        company.research_status = "queued"
    else:
        company.research_status = "not_started"

    db.add(company)
    db.commit()
    db.refresh(company)

    if company.website and reserve_onboarding(company.id):
        # Use the exact engine selected by this request (including test and
        # temporary databases), never the module-global development database.
        factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        background_tasks.add_task(
            run_company_onboarding,
            company.id,
            factory,
        )

    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    companies = (
        db.query(Company)
        .order_by(Company.created_at.desc())
        .all()
    )
    legacy_company_ids = [
        company.id
        for company in companies
        if company.research_status in {"pending", "not_started"}
    ]
    latest_run_statuses = {}
    if legacy_company_ids:
        rows = (
            db.query(ResearchRun.company_id, ResearchRun.status)
            .filter(ResearchRun.company_id.in_(legacy_company_ids))
            .order_by(ResearchRun.started_at.desc())
            .all()
        )
        for row in rows:
            latest_run_statuses.setdefault(row.company_id, row.status)
    return [
        _company_response(company, latest_run_statuses.get(company.id))
        for company in companies
    ]


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: str,
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    latest_run = None
    if company.research_status in {"pending", "not_started"}:
        latest_run = (
            db.query(ResearchRun)
            .filter(ResearchRun.company_id == company_id)
            .order_by(ResearchRun.started_at.desc())
            .first()
        )
    return _company_response(
        company,
        latest_run.status if latest_run is not None else None,
    )


@router.post("/{company_id}/research")
def start_research(
    company_id: str,
    background_tasks: BackgroundTasks,
    max_pages: int = Query(default=12, ge=1, le=12),
    search_depth: int = Query(default=4, ge=1, le=6),
    background: bool = Query(
        default=False,
        description="Queue the existing bounded research-to-ingestion worker and return immediately.",
    ),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    if not company.website:
        raise HTTPException(
            status_code=400,
            detail="Company does not have a website configured.",
        )

    if background:
        if not reserve_onboarding(company_id):
            return JSONResponse(status_code=202, content={
                "company_id": company_id,
                "company_name": company.name,
                "status": "running",
                "already_running": True,
                "counts": {},
                "results": [],
            })

        company.research_status = "queued"
        db.commit()
        factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        background_tasks.add_task(
            run_company_onboarding,
            company_id,
            factory,
        )
        return JSONResponse(status_code=202, content={
            "company_id": company_id,
            "company_name": company.name,
            "status": "queued",
            "already_running": False,
            "counts": {},
            "results": [],
        })

    if company.research_status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Company research is already in progress.",
        )

    try:
        result = collect_company_sources(
            db=db,
            company_id=company_id,
            max_pages=max_pages,
            search_depth=search_depth,
        )
        counts = result.get("counts") or {}
        if counts.get("failed", 0) or result.get("discovery_errors"):
            company.research_status = (
                "partial" if counts.get("collected", 0) or result.get("discovery_errors") else "failed"
            )
        else:
            company.research_status = "completed"
        db.commit()
        return result

    except SourceDiscoveryError as exc:
        company.research_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        company.research_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/{company_id}/sources",
    response_model=list[SourceOut],
)
def list_sources(
    company_id: str,
    db: Session = Depends(get_db),
):
    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company_id,
            SourceDocument.permission_status == "public",
        )
        .order_by(SourceDocument.collected_at.desc())
        .all()
    )


@router.get(
    "/{company_id}/events",
    response_model=list[EventOut],
)
def list_events(
    company_id: str,
    db: Session = Depends(get_db),
):
    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    events = (
        db.query(ProductEvent)
        .filter_by(company_id=company_id)
        .all()
    )

    if not events:
        return []

    event_ids = [event.id for event in events]

    source_rows = db.execute(
        select(
            event_sources.c.event_id,
            event_sources.c.source_id,
            SourceDocument.permission_status,
        )
        .join(
            SourceDocument,
            SourceDocument.id == event_sources.c.source_id,
        )
        .where(
            event_sources.c.event_id.in_(event_ids),
            SourceDocument.company_id == company_id,
        )
    ).all()

    source_ids_by_event = {}
    all_source_ids_by_event = {}

    for event_id, source_id, permission_status in source_rows:
        all_source_ids_by_event.setdefault(event_id, set()).add(source_id)
        if permission_status == "public":
            source_ids_by_event.setdefault(event_id, []).append(source_id)

    response = []

    for event in events:
        public_source_ids = source_ids_by_event.get(event.id, [])
        all_source_ids = all_source_ids_by_event.get(event.id, set())
        if not public_source_ids or not all_source_ids.issubset(
            set(public_source_ids)
        ):
            continue

        response.append(
            {
                "id": event.id,
                "company_id": event.company_id,
                "product_name": event.product_name,
                "event_type": event.event_type,
                "title": event.title,
                "description": event.description,
                "event_date": event.event_date,
                "stated_reason": event.stated_reason,
                "reported_outcome": event.reported_outcome,
                "evidence_classification": (
                    event.evidence_classification
                ),
                "source_ids": public_source_ids,
            }
        )

    return response
