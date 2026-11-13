from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, KnowledgeItem, SourceDocument


_GENERIC_TERMS = {
    "about", "after", "also", "been", "does", "from", "have", "into",
    "more", "most", "that", "them", "there", "these", "they", "this",
    "what", "when", "where", "which", "with", "will", "would", "company",
    "product", "products", "event", "events", "history", "documented",
}


def append_relevant_knowledge_item_passages(
    db: Session,
    *,
    company_id: str,
    query: str,
    retrieved_passages: list[dict[str, Any]],
    include_authorized_internal: bool = False,
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """Add only exact, source-backed knowledge quotes from retrieved sources.

    Knowledge items do not create independent source provenance: a quote must
    still occur verbatim in its linked SourceDocument, and the source must have
    been selected by ordinary semantic retrieval first.
    """
    if not retrieved_passages:
        return retrieved_passages
    permitted = {"public"}
    if include_authorized_internal:
        permitted.add("authorized_internal")
    source_rank: dict[str, float] = {}
    existing_by_source: dict[str, list[str]] = {}
    for passage in retrieved_passages:
        source_id = passage.get("source_id")
        if not isinstance(source_id, str):
            continue
        source_rank[source_id] = max(
            source_rank.get(source_id, -1.0),
            float(passage.get("similarity") or 0.0),
        )
        existing_by_source.setdefault(source_id, []).append(
            str(passage.get("chunk_text") or "")
        )
    if not source_rank:
        return retrieved_passages

    query_terms = {
        token for token in re.findall(r"[a-z0-9]+", query.casefold())
        if len(token) >= 4 and token not in _GENERIC_TERMS
    }
    rows = (
        db.query(KnowledgeItem, SourceDocument)
        .join(SourceDocument, KnowledgeItem.source_id == SourceDocument.id)
        .filter(
            KnowledgeItem.company_id == company_id,
            KnowledgeItem.source_id.in_(list(source_rank)),
            SourceDocument.permission_status.in_(permitted),
        )
        .order_by(KnowledgeItem.extraction_confidence.desc())
        .all()
    )
    company = db.get(Company, company_id)
    added = 0
    seen_quotes = {
        (source_id, " ".join(text.casefold().split()))
        for source_id, texts in existing_by_source.items()
        for text in texts
    }
    for item, source in rows:
        if added >= max_items:
            break
        quote = item.evidence_quote.strip()
        if not quote or quote not in (source.content_text or ""):
            continue
        item_terms = set(re.findall(
            r"[a-z0-9]+",
            " ".join((item.title or "", item.subject_name or "", quote)).casefold(),
        ))
        if query_terms and not query_terms.intersection(item_terms):
            continue
        normalized = " ".join(quote.casefold().split())
        key = (source.id, normalized)
        if key in seen_quotes:
            continue
        # Avoid adding a quote already contained in any selected passage.
        if any(
            normalized in " ".join(text.casefold().split())
            or " ".join(text.casefold().split()) in normalized
            for text in existing_by_source.get(source.id, [])
            if text.strip()
        ):
            continue
        metadata = source.source_metadata if isinstance(source.source_metadata, dict) else {}
        scope = (
            "authorized_internal"
            if source.permission_status == "authorized_internal"
            else "public_company"
        )
        retrieved_passages.append({
            "source_id": source.id,
            "source_company_id": company_id,
            "source_company_name": company.name if company else None,
            "source_title": source.title,
            "source_url": source.url,
            "chunk_index": None,
            "chunk_text": quote,
            "similarity": source_rank[source.id],
            "permission_status": source.permission_status,
            "evidence_scope": scope,
            "evidence_origin": metadata.get("evidence_origin", scope),
            "knowledge_item_id": item.id,
            "knowledge_item_type": item.item_type,
            "evidence_classification": item.evidence_classification,
            "extraction_confidence": item.extraction_confidence,
            "evidence_quote": quote,
        })
        seen_quotes.add(key)
        existing_by_source.setdefault(source.id, []).append(quote)
        added += 1
    return retrieved_passages
