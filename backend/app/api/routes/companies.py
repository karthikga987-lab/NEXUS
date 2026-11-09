
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company, SourceDocument, ProductEvent
from app.schemas.contracts import (
    CompanyCreate,
    CompanyOut,
    SourceOut,
    EventOut,
)

from app.research.discovery import discover_sources
from app.research.fetcher import fetch_url
from app.research.processor import extract_text
from app.research.persistence import save_source
from app.research.event_extracter import extract_events
from app.research.event_persistence import save_events


router = APIRouter()


@router.post("", response_model=CompanyOut, status_code=201)
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
    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return company


@router.post("/{company_id}/research")
def start_research(company_id: str, db: Session = Depends(get_db)):

    print("RESEARCH ENDPOINT CALLED", flush=True)

    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    if not company.website:
        raise HTTPException(
            status_code=400,
            detail="Company does not have a website",
        )

    print("DISCOVERING SOURCES...", flush=True)

    urls = discover_sources(company.website)

    print("DISCOVERED URLS:", urls, flush=True)

    collected = 0
    failed = 0

    for url in urls:

        print("CALLING FETCHER:", url, flush=True)

        html = fetch_url(url)

        if not html:
            print("FETCH FAILED:", url, flush=True)
            failed += 1
            continue

        print("FETCH SUCCESSFUL:", url, flush=True)

        text = extract_text(html)

        if not text.strip():
            print("TEXT EXTRACTION FAILED:", url, flush=True)
            failed += 1
            continue

        print("TEXT EXTRACTED SUCCESSFULLY", flush=True)

        save_source(
            db=db,
            company_id=company.id,
            url=url,
            text=text,
        )

        collected += 1

    print("RESEARCH COMPLETED", flush=True)

    return {
        "company_id": company.id,
        "status": "completed",
        "sources_collected": collected,
        "sources_failed": failed,
    }


@router.get("/{company_id}/sources", response_model=list[SourceOut])
def list_sources(company_id: str, db: Session = Depends(get_db)):

    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return (
        db.query(SourceDocument)
        .filter_by(company_id=company_id)
        .all()
    )


@router.get("/{company_id}/events", response_model=list[EventOut])
def list_events(company_id: str, db: Session = Depends(get_db)):

    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return (
        db.query(ProductEvent)
        .filter_by(company_id=company_id)
        .all()
    )


@router.post("/{company_id}/extract-events")
def extract_company_events(
    company_id: str,
    db: Session = Depends(get_db),
):
    # 1. Check whether the company exists
    company = db.get(Company, company_id)

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    # 2. Get all collected sources belonging to this company
    sources = (
        db.query(SourceDocument)
        .filter_by(company_id=company_id)
        .all()
    )

    if not sources:
        return {
            "status": "completed",
            "message": "No sources available for event extraction",
            "sources_processed": 0,
            "sources_failed": 0,
            "events_created": 0,
            "events_updated": 0,
        }

    # 3. Keep track of the results
    sources_processed = 0
    sources_failed = 0
    total_created = 0
    total_updated = 0

    # 4. Process each source
    for source in sources:

        if not source.content_text or not source.content_text.strip():
            sources_failed += 1
            continue

        try:
            # Ask Gemini to extract events
            extracted = extract_events(
                company.name,
                source.content_text,
            )

            # Save extracted events in the database
            result = save_events(
                db=db,
                company_id=company.id,
                source_id=source.id,
                events=extracted,
            )

            sources_processed += 1
            total_created += result["events_created"]
            total_updated += result["events_updated"]

        except Exception as error:
            print(
                f"Event extraction failed for source {source.id}: {error}",
                flush=True,
            )
            sources_failed += 1

    return {
        "company_id": company.id,
        "status": "completed",
        "sources_processed": sources_processed,
        "sources_failed": sources_failed,
        "events_created": total_created,
        "events_updated": total_updated,
    }
