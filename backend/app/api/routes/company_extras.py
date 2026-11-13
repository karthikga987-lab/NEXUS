from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.local_access import require_local_internal_access
from app.db.session import get_db
from app.intelligence.embeddings import EmbeddingError, search_similar_chunks
from app.models import Company, KnowledgeItem, ResearchRun, SourceDocument
from app.models.entities import feedback_topics
from app.feedback.queries import list_public_company_feedback
from app.research.persistence import save_internal_source
from app.research.status import effective_research_status

router = APIRouter()
MAX_INTERNAL_DOCUMENT_BYTES = 1_000_000


def _metadata(source: SourceDocument) -> dict:
    return source.source_metadata if isinstance(source.source_metadata, dict) else {}


def _source_response(source: SourceDocument, *, include_content: bool = False) -> dict:
    metadata = _metadata(source)
    response = {
        "id": source.id,
        "company_id": source.company_id,
        "url": source.url,
        "title": source.title,
        "publisher": source.publisher,
        "source_type": source.source_type,
        "publication_date": source.publication_date,
        "collected_at": source.collected_at,
        "permission_status": source.permission_status,
        "processing_status": source.processing_status,
        "processing_failed_stage": source.processing_failed_stage,
        "processing_error": source.processing_error,
        "original_filename": metadata.get("original_filename"),
        "author": metadata.get("author"),
        "recorded_at": metadata.get("recorded_at"),
        "evidence_origin": metadata.get("evidence_origin"),
        "is_synthetic": bool(metadata.get("is_synthetic", False)),
    }
    if include_content:
        response["content_text"] = source.content_text
    return response


@router.get("/{company_id}/research-stats")
def get_research_stats(company_id: str, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    run = (
        db.query(ResearchRun)
        .filter(ResearchRun.company_id == company_id)
        .order_by(ResearchRun.started_at.desc())
        .first()
    )
    return {
        "company_id": company_id,
        "research_status": effective_research_status(
            company.research_status,
            run.status if run is not None else None,
        ),
        "latest_run": None if run is None else {
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "counts": run.counts or {},
            "failure_summary": run.failure_summary,
        },
    }


@router.get("/{company_id}/feedback")
def list_company_feedback(company_id: str, db: Session = Depends(get_db)):
    """Return the selected company's public or unlinked feedback records."""
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")

    records = list_public_company_feedback(db, company_id)
    topics_by_feedback: dict[str, list[str]] = {}
    if records:
        rows = db.execute(
            feedback_topics.select().where(
                feedback_topics.c.feedback_id.in_([record.id for record in records])
            )
        ).all()
        for row in rows:
            topics_by_feedback.setdefault(row.feedback_id, []).append(row.topic)

    items = [{
        "id": item.id,
        "company_id": item.company_id,
        "product_name": item.product_name,
        "source_id": item.source_id,
        "source_url": item.source_url,
        "external_reference": item.external_reference,
        "feedback_text": item.feedback_text,
        "rating": item.rating,
        "language": item.language,
        "created_at_source": item.created_at_source,
        "collected_at": item.collected_at,
        "sentiment": item.sentiment,
        "topics": sorted(set(topics_by_feedback.get(item.id, []))),
        "feedback_type": item.feedback_type,
        "analysis_status": item.analysis_status,
    } for item in records]
    return {"company_id": company_id, "total": len(items), "items": items}


@router.post("/{company_id}/internal-sources", status_code=201)
async def import_internal_source(
    company_id: str,
    request: Request,
    file: UploadFile = File(...),
    author: str | None = Form(default=None),
    recorded_at: datetime | None = Form(default=None),
    source_identifier: str | None = Form(default=None),
    is_synthetic: bool = Form(default=False),
    db: Session = Depends(get_db),
):
    require_local_internal_access(request)
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    filename = file.filename or ""
    if not filename.casefold().endswith((".txt", ".md")):
        raise HTTPException(status_code=415, detail="Only .txt and .md documents are supported.")
    raw = await file.read(MAX_INTERNAL_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_INTERNAL_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 1 MB import limit.")
    try:
        content = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Document must be valid UTF-8 text.") from exc
    if "\x00" in content:
        raise HTTPException(status_code=400, detail="Binary content is not supported.")
    try:
        source, created, unchanged = save_internal_source(
            db,
            company_id,
            filename,
            content,
            source_identifier=source_identifier,
            author=author,
            recorded_at=recorded_at,
            is_synthetic=is_synthetic,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = _source_response(source)
    response.update({"created": created, "unchanged": unchanged})
    response["next_step"] = (
        "From trusted local development, process this company with "
        "include_authorized_internal=true to extract evidence and embeddings."
    )
    return response


@router.get("/{company_id}/internal-sources")
def list_internal_sources(
    company_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    require_local_internal_access(request)
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    sources = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company_id,
            SourceDocument.permission_status == "authorized_internal",
        )
        .order_by(SourceDocument.collected_at.desc())
        .all()
    )
    return [_source_response(source) for source in sources]


@router.get("/{company_id}/internal-sources/{source_id}")
def get_internal_source(
    company_id: str,
    source_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    require_local_internal_access(request)
    source = db.get(SourceDocument, source_id)
    if (
        source is None
        or source.company_id != company_id
        or source.permission_status != "authorized_internal"
    ):
        raise HTTPException(status_code=404, detail="Internal source not found")
    return _source_response(source, include_content=True)


@router.get("/{company_id}/sources/{source_id}")
def get_public_source(
    company_id: str,
    source_id: str,
    db: Session = Depends(get_db),
):
    source = db.get(SourceDocument, source_id)
    if source is None or source.company_id != company_id or source.permission_status != "public":
        raise HTTPException(status_code=404, detail="Source not found")
    metadata = _metadata(source)
    return {
        **_source_response(source, include_content=True),
        "content_kind": metadata.get("content_kind", "full_document"),
        "source_category": metadata.get("source_category"),
        "discovery_method": metadata.get("discovery_method"),
    }


@router.get("/{company_id}/knowledge-items")
def list_knowledge_items(
    company_id: str,
    request: Request,
    query: str | None = Query(default=None, min_length=3, max_length=2000),
    include_authorized_internal: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if include_authorized_internal:
        require_local_internal_access(request)
    allowed_permissions = ["public"]
    if include_authorized_internal:
        allowed_permissions.append("authorized_internal")

    source_ids = None
    if query:
        try:
            matches = search_similar_chunks(
                db=db,
                query=query,
                company_id=company_id,
                limit=min(limit * 3, 100),
                include_authorized_internal=include_authorized_internal,
            )
        except EmbeddingError as exc:
            raise HTTPException(status_code=503, detail=f"Knowledge retrieval unavailable: {exc}") from exc
        source_ids = list(dict.fromkeys(item["source_id"] for item in matches))
        if not source_ids:
            return []

    rows_query = (
        db.query(KnowledgeItem, SourceDocument)
        .join(SourceDocument, KnowledgeItem.source_id == SourceDocument.id)
        .filter(
            KnowledgeItem.company_id == company_id,
            SourceDocument.permission_status.in_(allowed_permissions),
        )
    )
    if source_ids is not None:
        rows_query = rows_query.filter(KnowledgeItem.source_id.in_(source_ids))
    rows = rows_query.order_by(KnowledgeItem.created_at.desc()).limit(limit).all()
    results = []
    for item, source in rows:
        if item.evidence_quote not in (source.content_text or ""):
            continue
        metadata = _metadata(source)
        results.append({
            "id": item.id,
            "company_id": item.company_id,
            "source_id": item.source_id,
            "item_type": item.item_type,
            "title": item.title,
            "description": item.description,
            "subject_name": item.subject_name,
            "actor": item.actor,
            "status": item.status,
            "item_date": item.item_date,
            "evidence_quote": item.evidence_quote,
            "evidence_classification": item.evidence_classification,
            "extraction_confidence": item.extraction_confidence,
            "created_at": item.created_at,
            "collected_at": item.collected_at,
            "source_title": source.title,
            "source_url": source.original_url or source.url,
            "permission_status": source.permission_status,
            "evidence_origin": metadata.get(
                "evidence_origin",
                "authorized_internal" if source.permission_status == "authorized_internal" else "public_company",
            ),
            "is_synthetic": bool(metadata.get("is_synthetic", False)),
        })
    return results
