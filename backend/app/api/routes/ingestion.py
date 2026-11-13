from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.local_access import require_local_internal_access
from app.intelligence.ingestion import (
    get_company_ingestion_status,
    process_company_sources,
)


router = APIRouter()


@router.post("/companies/{company_id}/process")
def process_company(
    company_id: str,
    source_ids: list[str] | None = Body(
        default=None,
        embed=True,
    ),
    limit: int = Query(default=25, ge=1, le=100),
    force: bool = Query(default=False),
    include_authorized_internal: bool = Query(default=False),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Process stored documents for a company.

    No URL discovery or fetching takes place in this endpoint.

    Body:
        {
            "source_ids": ["optional-source-id"]
        }

    If source_ids is omitted or null, pending and failed sources
    are processed. Set force=true to reprocess already processed
    sources as well.
    """
    if include_authorized_internal:
        if request is None:
            raise HTTPException(status_code=403, detail="Authorized internal ingestion is only available through the trusted local API.")
        require_local_internal_access(request)
    try:
        return process_company_sources(
            db=db,
            company_id=company_id,
            source_ids=source_ids,
            limit=limit,
            force=force,
            include_authorized_internal=include_authorized_internal,
        )

    except ValueError as exc:
        message = str(exc)

        if message.startswith("Company not found"):
            raise HTTPException(
                status_code=404,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=400,
            detail=message,
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Company ingestion failed: {str(exc)}",
        ) from exc


@router.get("/companies/{company_id}/status")
def company_ingestion_status(
    company_id: str,
    request: Request,
    include_authorized_internal: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Get stored processing status for evidence accessible to this caller."""
    if include_authorized_internal:
        require_local_internal_access(request)
    try:
        return get_company_ingestion_status(
            db=db,
            company_id=company_id,
            include_authorized_internal=include_authorized_internal,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
