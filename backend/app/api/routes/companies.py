from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models import (
    Company,
    EventRelationship,
    InternalSource,
    KnowledgeItem,
    ProductEvent,
    SourceDocument,
)
from app.research.discovery import discover_sources
from app.research.event_extracter import extract_events
from app.research.event_persistence import save_events
from app.research.fetcher import fetch_url
from app.research.persistence import (
    calculate_hash,
    find_source_by_url,
    save_internal_source,
    save_source,
    save_source_failure,
)
from app.research.processor import process_html
from app.schemas.contracts import CompanyCreate, CompanyOut


router = APIRouter()
RECENT_FAILURE_WINDOW = timedelta(hours=6)
MIN_SEARCH_SNIPPET_LENGTH = 80


class InternalSourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=40)
    content_text: str = Field(min_length=1)
    source_identifier: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=1000)
    author: str | None = Field(default=None, max_length=255)
    recorded_at: datetime | None = None
    is_synthetic: bool | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None


class EventRelationshipCreate(BaseModel):
    from_event_id: str
    to_event_id: str
    relation_type: Literal[
        "PRECEDED_BY",
        "MOTIVATED_BY",
        "APPROVED_BY",
        "TESTED_THROUGH",
        "RESULTED_IN",
        "RECEIVED_FEEDBACK",
        "CHANGED_BECAUSE_OF",
    ]
    source_ids: list[str] = Field(min_length=1)
    evidence_classification: Literal[
        "documented_cause",
        "supported_relationship",
        "correlation",
        "unknown",
    ] = "unknown"
    explanation: str = Field(min_length=1)


def _company_or_404(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _public_source_type(owner_type: str) -> str:
    return {
        "target_company": "company_website",
        "regulator": "regulatory_source",
        "news_organization": "news_article",
    }.get(owner_type, "public_webpage")


def _safe_error(error: Exception) -> str:
    message = str(error)
    if settings.gemini_api_key:
        message = message.replace(settings.gemini_api_key, "[redacted]")
    return message[:500]


def _extract_and_save_source(
    db: Session,
    company: Company,
    source: SourceDocument | InternalSource,
    source_kind: str,
) -> dict:
    current_hash = calculate_hash(source.content_text)
    if source.extraction_hash == current_hash:
        return {
            "skipped": True,
            "events_created": 0,
            "events_updated": 0,
            "knowledge_items_created": 0,
            "knowledge_items_updated": 0,
        }

    extracted = extract_events(
        company.name,
        source.content_text,
        source_type=source.source_type,
        source_title=source.title,
        source_kind=source_kind,
        is_synthetic=bool(getattr(source, "is_synthetic", False)),
    )
    result = save_events(
        db=db,
        company_id=company.id,
        source_id=source.id,
        result=extracted,
        source_kind=source_kind,
        source_type=source.source_type,
    )
    source.processing_status = "completed"
    source.content_hash = current_hash
    source.extraction_hash = current_hash
    db.commit()
    return result


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = Company(**payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.created_at.desc()).all()


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: str, db: Session = Depends(get_db)):
    return _company_or_404(db, company_id)


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: str,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
):
    company = _company_or_404(db, company_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


@router.get("/{company_id}/sources")
def list_sources(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    return db.query(SourceDocument).filter_by(company_id=company_id).all()


@router.get("/{company_id}/sources/{source_id}")
def get_source(company_id: str, source_id: str, db: Session = Depends(get_db)):
    source = db.query(SourceDocument).filter_by(
        company_id=company_id, id=source_id
    ).first()
    if not source:
        internal = db.query(InternalSource).filter_by(
            company_id=company_id, id=source_id
        ).first()
        if not internal:
            raise HTTPException(status_code=404, detail="Source not found")
        return internal
    return source


@router.post("/{company_id}/internal-sources", status_code=status.HTTP_201_CREATED)
def ingest_internal_source(
    company_id: str,
    payload: InternalSourceCreate,
    db: Session = Depends(get_db),
):
    _company_or_404(db, company_id)
    try:
        source, created = save_internal_source(
            db=db,
            company_id=company_id,
            **payload.model_dump(),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"source": source, "created": created, "status": source.processing_status}


@router.get("/{company_id}/internal-sources")
def list_internal_sources(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    return db.query(InternalSource).filter_by(company_id=company_id).all()


@router.get("/{company_id}/events")
def list_events(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    return db.query(ProductEvent).filter_by(company_id=company_id).all()


@router.get("/{company_id}/knowledge-items")
def list_knowledge_items(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    items = db.query(KnowledgeItem).filter_by(company_id=company_id).all()
    return {"company_id": company_id, "knowledge_items": items}


@router.get("/{company_id}/event-relationships")
def list_event_relationships(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    event_ids = [
        row[0]
        for row in db.query(ProductEvent.id).filter_by(company_id=company_id).all()
    ]
    if not event_ids:
        return {"company_id": company_id, "relationships": []}
    relationships = db.query(EventRelationship).filter(
        EventRelationship.from_event_id.in_(event_ids),
        EventRelationship.to_event_id.in_(event_ids),
    ).all()
    return {"company_id": company_id, "relationships": relationships}


@router.post("/{company_id}/event-relationships", status_code=status.HTTP_201_CREATED)
def create_event_relationship(
    company_id: str,
    payload: EventRelationshipCreate,
    db: Session = Depends(get_db),
):
    _company_or_404(db, company_id)
    if payload.from_event_id == payload.to_event_id:
        raise HTTPException(status_code=422, detail="An event cannot relate to itself")

    related_events = db.query(ProductEvent).filter(
        ProductEvent.company_id == company_id,
        ProductEvent.id.in_([payload.from_event_id, payload.to_event_id]),
    ).all()
    if len(related_events) != 2:
        raise HTTPException(status_code=404, detail="Related event not found")

    for source_id in payload.source_ids:
        public_source = db.query(SourceDocument.id).filter_by(
            id=source_id, company_id=company_id
        ).first()
        internal_source = db.query(InternalSource.id).filter_by(
            id=source_id, company_id=company_id
        ).first()
        if not public_source and not internal_source:
            raise HTTPException(status_code=422, detail="Relationship source is not owned by this company")
        supports_an_event = any(
            source_id in (event.source_ids or [])
            or any(
                reference.get("source_id") == source_id
                for reference in (event.source_references or [])
            )
            for event in related_events
        )
        if not supports_an_event:
            raise HTTPException(
                status_code=422,
                detail="Relationship source must support at least one related event",
            )

    relationship = db.query(EventRelationship).filter_by(
        from_event_id=payload.from_event_id,
        to_event_id=payload.to_event_id,
        relation_type=payload.relation_type,
    ).first()
    created = relationship is None
    if relationship is None:
        relationship = EventRelationship(
            from_event_id=payload.from_event_id,
            to_event_id=payload.to_event_id,
            relation_type=payload.relation_type,
            source_ids=[],
        )
        db.add(relationship)
    relationship.source_ids = list(dict.fromkeys(
        [*(relationship.source_ids or []), *payload.source_ids]
    ))
    relationship.evidence_classification = payload.evidence_classification
    relationship.explanation = payload.explanation or relationship.explanation
    db.commit()
    db.refresh(relationship)
    return {"relationship": relationship, "created": created}


@router.get("/{company_id}/research-stats")
def research_stats(company_id: str, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    public = db.query(SourceDocument).filter_by(company_id=company_id).all()
    internal = db.query(InternalSource).filter_by(company_id=company_id).all()
    public_extracted = sum(
        bool(source.content_hash and source.extraction_hash == source.content_hash)
        for source in public
        if source.content_kind != "search_snippet"
    )
    internal_extracted = sum(
        bool(source.content_hash and source.extraction_hash == source.content_hash)
        for source in internal
    )
    event_ids = [
        row[0]
        for row in db.query(ProductEvent.id).filter_by(company_id=company_id).all()
    ]
    relationship_count = (
        db.query(EventRelationship)
        .filter(EventRelationship.from_event_id.in_(event_ids))
        .count()
        if event_ids
        else 0
    )
    return {
        "company_id": company_id,
        "public_sources": {
            "total": len(public),
            "fetched": sum(
                source.content_kind == "full_page"
                and source.processing_status == "completed"
                for source in public
            ),
            "snippets": sum(source.content_kind == "search_snippet" for source in public),
            "failed": sum(source.processing_status == "failed" for source in public),
        },
        "internal_sources": len(internal),
        "sources_extracted": public_extracted + internal_extracted,
        "sources_pending_extraction": (
            sum(source.content_kind != "search_snippet" for source in public)
            + len(internal)
            - public_extracted
            - internal_extracted
        ),
        "events": db.query(ProductEvent).filter_by(company_id=company_id).count(),
        "knowledge_items": db.query(KnowledgeItem).filter_by(company_id=company_id).count(),
        "event_relationships": relationship_count,
    }


def _collect_candidate(
    db: Session, company_id: str, candidate: dict
) -> dict:
    counts = {
        "sources_fetched": 0,
        "sources_saved": 0,
        "sources_updated": 0,
        "sources_skipped": 0,
        "sources_failed": 0,
    }
    url = candidate["url"]
    prior = find_source_by_url(db, company_id, url)
    if prior and prior.fetch_error:
        updated_at = prior.updated_at or prior.collected_at
        if updated_at and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at and updated_at > datetime.now(timezone.utc) - RECENT_FAILURE_WINDOW:
            counts["sources_skipped"] = 1
            return counts

    fetched = fetch_url(url)
    metadata = {
        "source_owner_type": candidate["source_owner_type"],
        "is_target_company_official": candidate["is_target_company_official"],
        "is_other_company_official": candidate["is_other_company_official"],
        "source_authority_level": candidate["source_authority_level"],
        "discovery_method": candidate["discovery_method"],
        "search_query": candidate.get("search_query"),
    }

    if fetched.ok:
        document = process_html(fetched.content or "")
        if len(document.text.strip()) >= 40:
            counts["sources_fetched"] = 1
            previous_hash = prior.content_hash if prior else None
            source = save_source(
                db=db,
                company_id=company_id,
                url=url,
                text=document.text,
                title=document.title or candidate.get("search_title"),
                publisher=urlsplit(url).hostname,
                source_type=_public_source_type(candidate["source_owner_type"]),
                content_kind="full_page",
                **metadata,
            )
            if not prior:
                counts["sources_saved"] = 1
            elif previous_hash != source.content_hash:
                counts["sources_updated"] = 1
            else:
                counts["sources_skipped"] = 1
            return counts
        fetched = fetched.__class__(
            fetched.requested_url,
            fetched.final_url,
            status_code=fetched.status_code,
            error="Page contained too little readable text",
        )

    snippet = "\n\n".join(
        part.strip()
        for part in (candidate.get("search_title"), candidate.get("search_snippet"))
        if isinstance(part, str) and part.strip()
    )
    if len(snippet) >= MIN_SEARCH_SNIPPET_LENGTH:
        if prior and prior.content_kind == "full_page" and prior.content_text:
            prior.fetch_error = fetched.error
            db.commit()
            counts["sources_skipped"] = 1
            counts["sources_failed"] = 1
            return {**counts, "error": fetched.error, "snippet_saved": False}

        previous_hash = prior.content_hash if prior else None
        source = save_source(
            db=db,
            company_id=company_id,
            url=url,
            text=snippet,
            title=candidate.get("search_title"),
            publisher=urlsplit(url).hostname,
            source_type="search_result",
            content_kind="search_snippet",
            processing_status="partial",
            fetch_error=fetched.error,
            **metadata,
        )
        if not prior:
            counts["sources_saved"] = 1
        elif previous_hash != source.content_hash:
            counts["sources_updated"] = 1
        else:
            counts["sources_skipped"] = 1
        counts["sources_failed"] = 1
        return {**counts, "error": fetched.error, "snippet_saved": True}

    error = fetched.error or "No readable content or useful search snippet"
    failure_metadata = {
        **metadata,
        "title": candidate.get("search_title"),
        "publisher": urlsplit(url).hostname,
        "source_type": _public_source_type(candidate["source_owner_type"]),
    }
    save_source_failure(db, company_id, url, error, **failure_metadata)
    counts["sources_failed"] = 1
    return {**counts, "error": error}


@router.post("/{company_id}/research")
def research_company(company_id: str, db: Session = Depends(get_db)):
    company = _company_or_404(db, company_id)
    try:
        candidates = discover_sources(company.website, company.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    counts = {
        "sources_discovered": len(candidates),
        "sources_fetched": 0,
        "sources_saved": 0,
        "sources_updated": 0,
        "sources_skipped": 0,
        "sources_failed": 0,
    }
    errors = []

    for candidate in candidates:
        try:
            result = _collect_candidate(db, company.id, candidate)
        except Exception as error:
            db.rollback()
            result = {
                "sources_fetched": 0,
                "sources_saved": 0,
                "sources_updated": 0,
                "sources_skipped": 0,
                "sources_failed": 1,
                "error": _safe_error(error),
            }
        for key, value in result.items():
            if key in counts:
                counts[key] += value
        if result.get("error"):
            errors.append({
                "url": candidate["url"],
                "error": result["error"],
                "snippet_saved": result.get("snippet_saved", False),
            })

    all_failed = (
        counts["sources_failed"] == counts["sources_discovered"]
        and counts["sources_discovered"] > 0
        and counts["sources_saved"] == 0
        and counts["sources_updated"] == 0
    )
    has_errors = counts["sources_failed"] > 0
    return {
        "company_id": company.id,
        "status": "failed" if all_failed else "partial" if has_errors else "completed",
        **counts,
        "source_categories": _count_source_categories(candidates),
        "errors": errors,
    }


def _count_source_categories(candidates: list[dict]) -> dict[str, int]:
    categories: dict[str, int] = {}
    for candidate in candidates:
        category = candidate["source_owner_type"]
        categories[category] = categories.get(category, 0) + 1
    return categories


@router.post("/{company_id}/extract-events")
def extract_company_events(company_id: str, db: Session = Depends(get_db)):
    company = _company_or_404(db, company_id)
    sources = [
        (source, "public")
        for source in db.query(SourceDocument).filter_by(company_id=company_id).all()
        if source.content_text and source.content_kind != "search_snippet"
    ] + [
        (source, "internal")
        for source in db.query(InternalSource).filter_by(company_id=company_id).all()
        if source.content_text and source.content_text.strip()
    ]

    totals = {
        "sources_processed": 0,
        "sources_skipped": 0,
        "sources_failed": 0,
        "events_created": 0,
        "events_updated": 0,
        "knowledge_items_created": 0,
        "knowledge_items_updated": 0,
    }
    errors = []
    for source, kind in sources:
        try:
            result = _extract_and_save_source(db, company, source, kind)
            if result.get("skipped"):
                totals["sources_skipped"] += 1
                continue
            totals["sources_processed"] += 1
            for key in (
                "events_created",
                "events_updated",
                "knowledge_items_created",
                "knowledge_items_updated",
            ):
                totals[key] += result[key]
        except Exception as error:
            db.rollback()
            source.processing_status = "failed"
            db.commit()
            totals["sources_failed"] += 1
            errors.append({
                "source_id": source.id,
                "source_kind": kind,
                "error": _safe_error(error),
            })

    return {
        "company_id": company.id,
        "status": "partial" if errors else "completed",
        **totals,
        "errors": errors,
    }
