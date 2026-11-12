from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company, SourceDocument, ProductEvent
from app.models.entities import event_sources
from app.schemas.contracts import (
    CompanyCreate,
    CompanyOut,
    SourceOut,
    EventOut,
)
from app.research.service import collect_company_sources
from app.research.discovery import SourceDiscoveryError


router = APIRouter()


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
):
    company = Company(**payload.model_dump())

    db.add(company)
    db.commit()
    db.refresh(company)

    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return (
        db.query(Company)
        .order_by(Company.created_at.desc())
        .all()
    )


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

    return company


@router.post("/{company_id}/research")
def start_research(
    company_id: str,
    max_pages: int = Query(default=12, ge=1, le=12),
    search_depth: int = Query(default=4, ge=1, le=6),
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
