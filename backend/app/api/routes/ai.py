
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.local_access import require_local_internal_access
from app.models import Company, SourceDocument

from app.intelligence.embeddings import (
    EmbeddingError,
    search_similar_chunks,
    search_external_public_chunks,
)
from app.intelligence.rag import (
    RAGError,
    answer_with_evidence,
)


router = APIRouter()


class SemanticSearchRequest(BaseModel):
    company_id: str = Field(
        min_length=1,
        description="Company whose knowledge base is being searched.",
    )
    query: str = Field(
        min_length=3,
        max_length=2000,
        description="Natural-language search question.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum results per evidence scope.",
    )
    include_external_public: bool = Field(
        default=False,
        description="Whether to retrieve public evidence from other companies.",
    )
    include_authorized_internal: bool = False


class RAGAnswerRequest(BaseModel):
    company_id: str = Field(
        min_length=1,
        description="Company whose knowledge base should answer the question.",
    )
    query: str = Field(
        min_length=3,
        max_length=2000,
        description="Natural-language question.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum retrieved passages per evidence scope.",
    )
    include_external_public: bool = Field(
        default=False,
        description="Whether to include public evidence from other companies.",
    )
    include_authorized_internal: bool = False


@router.post("/search", status_code=200)
def semantic_search(
    payload: SemanticSearchRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    company = db.get(Company, payload.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    if payload.include_authorized_internal:
        if request is None:
            raise HTTPException(status_code=403, detail="Authorized internal evidence is only available through the trusted local API.")
        require_local_internal_access(request)

    try:
        internal_results = search_similar_chunks(
            db=db,
            query=payload.query,
            company_id=payload.company_id,
            limit=payload.limit,
            include_authorized_internal=payload.include_authorized_internal,
        )

        formatted_internal = []

        for item in internal_results:
            source = db.get(SourceDocument, item["source_id"])

            if source is None:
                continue

            formatted_internal.append({
                "source_id": item["source_id"],
                "source_title": item.get("source_title"),
                "source_url": item.get("source_url"),
                "source_company_id": company.id,
                "source_company_name": company.name,
                "chunk_index": item.get("chunk_index"),
                "similarity": item.get("similarity"),
                "retrieved_passage": item.get("chunk_text"),
                "evidence_scope": item.get("evidence_scope", "public_company"),
                "evidence_origin": item.get("evidence_origin") or "public_company",
                "permission_status": source.permission_status,
                "evidence_classification": "unknown",
            })

        external_results = []

        if payload.include_external_public:
            external_results = search_external_public_chunks(
                db=db,
                query=payload.query,
                exclude_company_id=payload.company_id,
                limit=payload.limit,
            )

        formatted_external = [
            {
                "source_id": item.get("source_id"),
                "source_title": item.get("source_title"),
                "source_url": item.get("source_url"),
                "source_company_id": item.get("source_company_id"),
                "source_company_name": item.get("source_company_name"),
                "chunk_index": item.get("chunk_index"),
                "similarity": item.get("similarity"),
                "retrieved_passage": item.get("chunk_text"),
                "evidence_scope": "external_public",
                "permission_status": item.get("permission_status"),
                "evidence_classification": "unknown",
            }
            for item in external_results
        ]

        return {
            "company_id": company.id,
            "company_name": company.name,
            "query": payload.query,
            "internal_result_count": len(formatted_internal),
            "authorized_internal_result_count": sum(1 for item in formatted_internal if item.get("permission_status") == "authorized_internal"),
            "external_public_result_count": len(formatted_external),
            "internal_evidence": formatted_internal,
            "external_public_evidence": formatted_external,
            "limitations": [
                "Semantic similarity measures relevance, not factual correctness.",
                "Retrieved passages are evidence candidates and have not independently verified every claim.",
                "Evidence classification remains unknown until claims are separately validated.",
                "Chronological sequence does not establish causation.",
            ],
        }

    except EmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Semantic search service unavailable: {exc}",
        ) from exc


@router.post("/answer", status_code=200)
def answer_question(
    payload: RAGAnswerRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    company = db.get(Company, payload.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    if payload.include_authorized_internal:
        if request is None:
            raise HTTPException(status_code=403, detail="Authorized internal evidence is only available through the trusted local API.")
        require_local_internal_access(request)

    try:
        return answer_with_evidence(
            db=db,
            company_id=payload.company_id,
            query=payload.query,
            limit=payload.limit,
            include_external_public=payload.include_external_public,
            include_authorized_internal=payload.include_authorized_internal,
        )

    except EmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Embedding service unavailable: {exc}",
        ) from exc

    except RAGError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"RAG service unavailable: {exc}",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
