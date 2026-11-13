
import hashlib
import logging
import re
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.embeddings import embed_source
from app.intelligence.extraction import extract_events
from app.models.entities import (
    Company,
    KnowledgeItem,
    ProductEvent,
    SourceDocument,
    event_sources,
)


logger = logging.getLogger(__name__)

ALLOWED_PERMISSION_STATUSES = {
    "public",
    "authorized_internal",
}

# These are ProductEvent evidence classifications from the NEXUS
# data contract. Do not confuse them with relationship classifications.
ALLOWED_EVENT_EVIDENCE_CLASSIFICATIONS = {
    "documented",
    "supported",
    "correlation",
    "unknown",
}

RETRYABLE_PROCESSING_STATUSES = {
    "pending",
    "failed",
    "processing",
    "collected",
}

DEFAULT_BATCH_SIZE = 25
MAX_BATCH_SIZE = 100


class IngestionError(Exception):
    """Raised when a company ingestion operation cannot be completed."""


def _normalize(value: str | None) -> str:
    if not isinstance(value, str):
        return ""

    return re.sub(r"\s+", " ", value).strip().casefold()


def _content_hash(content: str) -> str:
    normalized = " ".join(content.split())
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _event_datetime(value: Any) -> datetime | None:
    """
    Convert supported event-date values to UTC datetimes.

    Extraction currently returns YYYY-MM-DD strings, but this helper
    also supports ISO datetime strings for compatibility.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, date):
        parsed = datetime.combine(
            value,
            time.min,
            tzinfo=timezone.utc,
        )

    elif isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return None

        try:
            parsed_date = date.fromisoformat(normalized)
            parsed = datetime.combine(
                parsed_date,
                time.min,
                tzinfo=timezone.utc,
            )
        except ValueError:
            try:
                parsed = datetime.fromisoformat(
                    normalized.replace("Z", "+00:00")
                )
            except ValueError:
                return None

    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _same_event_date(
    existing: datetime | None,
    incoming: datetime | None,
) -> bool:
    if existing is None or incoming is None:
        return existing is None and incoming is None

    existing_utc = _event_datetime(existing)
    incoming_utc = _event_datetime(incoming)

    if existing_utc is None or incoming_utc is None:
        return False

    return existing_utc.date() == incoming_utc.date()


def _validate_event_evidence(
    event_data: dict[str, Any],
) -> tuple[str, str]:
    """
    Validate the event evidence classification and exact quotation.

    The extraction module already checks that the quotation occurs
    in the original source text. This function ensures the required
    evidence fields are present before database persistence.
    """
    evidence_classification = event_data.get("evidence_status")

    if evidence_classification not in ALLOWED_EVENT_EVIDENCE_CLASSIFICATIONS:
        raise IngestionError(
            "Extracted event has an unsupported evidence classification: "
            f"{evidence_classification!r}"
        )

    evidence_quote = event_data.get("evidence_quote")

    if not isinstance(evidence_quote, str) or not evidence_quote.strip():
        raise IngestionError(
            "Extracted event is missing its supporting evidence quotation."
        )

    return evidence_classification, evidence_quote.strip()


def _find_existing_event(
    db: Session,
    company_id: str,
    event_data: dict[str, Any],
) -> ProductEvent | None:
    """
    Conservative event deduplication.

    Events are considered duplicates only when company, product,
    event type, title and event date match. Similar-looking events
    are not merged automatically.
    """
    product_name = event_data.get("product_name")
    event_type = event_data.get("event_type")
    title = event_data.get("title")
    event_date = _event_datetime(event_data.get("event_date"))

    candidates = (
        db.query(ProductEvent)
        .filter(
            ProductEvent.company_id == company_id,
            ProductEvent.event_type == event_type,
        )
        .all()
    )

    for candidate in candidates:
        if _normalize(candidate.product_name) != _normalize(product_name):
            continue

        if _normalize(candidate.title) != _normalize(title):
            continue

        if not _same_event_date(candidate.event_date, event_date):
            continue

        return candidate

    return None


def _link_event_to_source(
    db: Session,
    event_id: str,
    source_id: str,
) -> None:
    existing_link = db.execute(
        select(event_sources.c.event_id).where(
            event_sources.c.event_id == event_id,
            event_sources.c.source_id == source_id,
        )
    ).first()

    if existing_link is None:
        db.execute(
            event_sources.insert().values(
                event_id=event_id,
                source_id=source_id,
            )
        )


def _persist_event(
    db: Session,
    company_id: str,
    source_id: str,
    event_data: dict[str, Any],
) -> tuple[ProductEvent, bool]:
    """
    Save an extracted event or link its source to an existing exact match.

    Returns:
        (event, created_new_event)
    """
    evidence_classification, _ = _validate_event_evidence(event_data)

    existing = _find_existing_event(
        db,
        company_id,
        event_data,
    )

    if existing is not None:
        _link_event_to_source(
            db,
            existing.id,
            source_id,
        )
        return existing, False

    event = ProductEvent(
        company_id=company_id,
        product_name=event_data.get("product_name"),
        event_type=event_data["event_type"],
        title=event_data["title"],
        description=event_data.get("description"),
        event_date=_event_datetime(event_data.get("event_date")),
        stated_reason=event_data.get("stated_reason"),
        reported_outcome=event_data.get("outcome_summary"),
        evidence_classification=evidence_classification,
        extraction_confidence=event_data.get(
            "extraction_confidence"
        ),
    )

    db.add(event)
    db.flush()

    _link_event_to_source(
        db,
        event.id,
        source_id,
    )

    return event, True


def _build_event_evidence_result(
    event: ProductEvent,
    source_id: str,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a response-level evidence record.

    The exact quotation is returned to the caller but is not stored
    independently in the current ProductEvent database schema.
    """
    evidence_classification, evidence_quote = _validate_event_evidence(
        event_data
    )

    return {
        "event_id": event.id,
        "source_id": source_id,
        "evidence_classification": evidence_classification,
        "evidence_quote": evidence_quote,
    }


def _persist_knowledge_item(
    db: Session,
    source: SourceDocument,
    item_data: dict[str, Any],
) -> tuple[KnowledgeItem, bool]:
    """Persist one exact-quote item and deduplicate within its source."""
    if source.company_id != item_data.get("company_id"):
        raise IngestionError(
            "Knowledge item company does not match its source company."
        )
    if source.id != item_data.get("source_id"):
        raise IngestionError(
            "Knowledge item source does not match the ingested document."
        )
    quote = item_data.get("evidence_quote")
    if not isinstance(quote, str) or quote not in (source.content_text or ""):
        raise IngestionError(
            "Knowledge item quotation is not an exact source excerpt."
        )

    existing = (
        db.query(KnowledgeItem)
        .filter(
            KnowledgeItem.company_id == source.company_id,
            KnowledgeItem.source_id == source.id,
            KnowledgeItem.item_type == item_data["item_type"],
            KnowledgeItem.evidence_quote == quote,
        )
        .first()
    )
    fields = {
        "title": item_data["title"],
        "description": item_data["description"],
        "subject_name": item_data.get("subject_name"),
        "actor": item_data.get("actor"),
        "status": item_data.get("status", "unknown"),
        "item_date": item_data.get("item_date"),
        "evidence_classification": item_data.get(
            "evidence_classification", "documented"
        ),
        "extraction_confidence": item_data.get("extraction_confidence"),
    }

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    item = KnowledgeItem(
        company_id=source.company_id,
        source_id=source.id,
        item_type=item_data["item_type"],
        evidence_quote=quote,
        collected_at=source.collected_at,
        **fields,
    )
    db.add(item)
    db.flush()
    return item, True


def _update_source_metadata(
    source: SourceDocument,
    updates: dict[str, Any],
) -> None:
    metadata = source.source_metadata

    if not isinstance(metadata, dict):
        metadata = {}

    metadata = dict(metadata)
    metadata.update(updates)
    source.source_metadata = metadata


def _mark_failed(
    db: Session,
    source_id: str,
    error: Exception,
    failed_stage: str,
    embedding_result: dict[str, Any] | None = None,
) -> None:
    db.rollback()

    source = db.get(SourceDocument, source_id)

    if source is None:
        return

    source.processing_status = "failed"

    updates = {
        "ingestion_error": str(error)[:1000],
        "ingestion_failed_stage": failed_stage,
        "ingestion_failed_at": datetime.now(timezone.utc).isoformat(),
    }

    if isinstance(embedding_result, dict):
        updates["embedding_chunks_created"] = embedding_result.get(
            "chunks_created", 0
        )
        updates["embedding_model"] = embedding_result.get("model")

    _update_source_metadata(source, updates)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Could not persist failed status for source %s",
            source_id,
        )
def _process_one_source(
    db: Session,
    source: SourceDocument,
    company_id: str,
    force: bool,
    include_authorized_internal: bool = False,
) -> dict[str, Any]:
    source_id = source.id

    if source.company_id != company_id:
        return {
            "source_id": source_id,
            "status": "skipped",
            "reason": "Source does not belong to this company.",
        }

    if (
        source.permission_status == "authorized_internal"
        and not include_authorized_internal
    ):
        return {
            "source_id": source_id,
            "status": "skipped",
            "reason": "Authorized internal sources require local access.",
        }

    if source.permission_status not in ALLOWED_PERMISSION_STATUSES:
        return {
            "source_id": source_id,
            "status": "skipped",
            "reason": (
                "Source permission status is not eligible for processing."
            ),
        }

    metadata = source.source_metadata
    if (
        isinstance(metadata, dict)
        and metadata.get("content_kind") == "search_snippet"
    ):
        return {
            "source_id": source_id,
            "status": "skipped",
            "reason": (
                "Search result snippets are discovery leads, not full "
                "documents, and are excluded from AI ingestion."
            ),
        }

    if source.processing_status == "processed" and not force:
        return {
            "source_id": source_id,
            "status": "skipped",
            "reason": "Source has already been processed.",
        }

    if not isinstance(source.content_text, str) or not source.content_text.strip():
        error = ValueError("Source document has no usable content.")
        _mark_failed(
            db,
            source_id,
            error,
            "source_validation",
        )

        return {
            "source_id": source_id,
            "status": "failed",
            "failed_stage": "source_validation",
            "error": str(error),
        }

    failed_stage = "source_initialization"
    embedding_result: dict[str, Any] | None = None

    try:
        source.processing_status = "processing"
        source.content_hash = _content_hash(source.content_text)

        _update_source_metadata(
            source,
            {
                "ingestion_started_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "ingestion_error": None,
                "ingestion_failed_stage": None,
            },
        )

        db.commit()

        # Stage 1: Generate and persist embeddings.
        failed_stage = "embedding"

        embedding_result = embed_source(
            db,
            source_id,
            include_authorized_internal=include_authorized_internal,
        )

        # Stage 2: Extract and validate product events.
        failed_stage = "event_extraction"

        extracted_events = extract_events(
            source_text=source.content_text,
            source_id=source_id,
            company_id=company_id,
        )
        extracted_knowledge_items = getattr(
            extracted_events,
            "knowledge_items",
            [],
        )

        new_event_count = 0
        linked_event_count = 0
        event_evidence = []
        source_event_evidence = []

        # Stage 3: Persist events and source relationships.
        failed_stage = "event_persistence"

        for event_data in extracted_events:
            event, created = _persist_event(
                db,
                company_id,
                source_id,
                event_data,
            )

            event_evidence.append(
                _build_event_evidence_result(
                    event=event,
                    source_id=source_id,
                    event_data=event_data,
                )
            )
            source_event_evidence.append({
                "event_id": event.id,
                "event_title": event.title,
                "event_date": event.event_date.isoformat() if event.event_date else None,
                "evidence_classification": event.evidence_classification,
                "extraction_confidence": event_data.get(
                    "extraction_confidence"
                ),
                "evidence_quote": event_data.get("evidence_quote"),
            })

            if created:
                new_event_count += 1
            else:
                linked_event_count += 1

        new_knowledge_item_count = 0
        linked_knowledge_item_count = 0
        knowledge_item_evidence = []
        failed_stage = "knowledge_item_persistence"
        for item_data in extracted_knowledge_items:
            item, created = _persist_knowledge_item(
                db,
                source,
                item_data,
            )
            knowledge_item_evidence.append({
                "knowledge_item_id": item.id,
                "source_id": source_id,
                "item_type": item.item_type,
                "evidence_quote": item.evidence_quote,
                "evidence_classification": item.evidence_classification,
            })
            if created:
                new_knowledge_item_count += 1
            else:
                linked_knowledge_item_count += 1

        # Stage 4: Finalize source processing.
        failed_stage = "finalization"

        source = db.get(SourceDocument, source_id)

        if source is None:
            raise IngestionError(
                "Source document disappeared during processing."
            )

        source.processing_status = "processed"

        _update_source_metadata(
            source,
            {
                "ingestion_completed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "ingestion_error": None,
                "ingestion_failed_stage": None,
                "extraction_event_count": len(extracted_events),
                "extraction_knowledge_item_count": len(
                    extracted_knowledge_items
                ),
                "new_event_count": new_event_count,
                "linked_existing_event_count": linked_event_count,
                "new_knowledge_item_count": new_knowledge_item_count,
                "linked_existing_knowledge_item_count": (
                    linked_knowledge_item_count
                ),
                "extracted_event_evidence": source_event_evidence,
                "embedding_chunks_created": embedding_result[
                    "chunks_created"
                ],
                "embedding_model": embedding_result["model"],
            },
        )

        db.commit()

        return {
            "source_id": source_id,
            "status": "processed",
            "events_extracted": len(extracted_events),
            "new_events": new_event_count,
            "existing_events_linked": linked_event_count,
            "knowledge_items_extracted": len(extracted_knowledge_items),
            "new_knowledge_items": new_knowledge_item_count,
            "existing_knowledge_items_linked": (
                linked_knowledge_item_count
            ),
            "embedding": embedding_result,
            "event_evidence": event_evidence,
            "knowledge_item_evidence": knowledge_item_evidence,
        }

    except Exception as exc:
        logger.exception(
            "Ingestion failed during %s for source %s",
            failed_stage,
            source_id,
        )

        _mark_failed(
            db,
            source_id,
            exc,
            failed_stage,
            embedding_result=embedding_result,
        )

        return {
            "source_id": source_id,
            "status": "failed",
            "failed_stage": failed_stage,
            "error": str(exc)[:1000],
            "embedding": embedding_result,
        }

def process_company_sources(
    db: Session,
    company_id: str,
    source_ids: list[str] | None = None,
    limit: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    include_authorized_internal: bool = False,
) -> dict[str, Any]:
    """
    Process existing source documents for one company.

    This function does not discover or fetch URLs. It processes only
    source records already stored in the database.

    Eligible operations:
    - permission validation
    - content hashing
    - event extraction and validation
    - conservative event deduplication
    - event-to-source linking
    - embedding generation
    - processing status and error tracking
    - response-level evidence quotation reporting
    """
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("A company ID is required.")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer.")

    if limit < 1 or limit > MAX_BATCH_SIZE:
        raise ValueError(
            f"limit must be between 1 and {MAX_BATCH_SIZE}."
        )

    company = db.get(Company, company_id)

    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    query = db.query(SourceDocument).filter(
        SourceDocument.company_id == company_id
    )

    if source_ids is not None:
        if not isinstance(source_ids, list) or not source_ids:
            raise ValueError(
                "source_ids must be a non-empty list when supplied."
            )

        unique_ids = list(dict.fromkeys(source_ids))

        if not all(
            isinstance(source_id, str) and source_id.strip()
            for source_id in unique_ids
        ):
            raise ValueError("Every source ID must be a non-empty string.")

        query = query.filter(
            SourceDocument.id.in_(unique_ids)
        )
    elif not force:
        query = query.filter(
            SourceDocument.processing_status.in_(
                RETRYABLE_PROCESSING_STATUSES
            )
        )

    sources = (
        query
        .order_by(SourceDocument.collected_at.asc())
        .limit(limit)
        .all()
    )

    if source_ids is not None:
        found_ids = {source.id for source in sources}
        missing_ids = set(source_ids) - found_ids

        if missing_ids:
            raise ValueError(
                "One or more source IDs do not belong to this company "
                "or could not be found."
            )

    results = []

    for source in sources:
        result = _process_one_source(
            db=db,
            source=source,
            company_id=company_id,
            force=force,
            include_authorized_internal=include_authorized_internal,
        )
        results.append(result)

    counts = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "events_extracted": 0,
        "new_events": 0,
        "existing_events_linked": 0,
        "knowledge_items_extracted": 0,
        "new_knowledge_items": 0,
        "existing_knowledge_items_linked": 0,
        "embedding_chunks_created": 0,
        "evidence_quotes_returned": 0,
    }

    for result in results:
        status = result.get("status")

        if status in counts:
            counts[status] += 1

        counts["events_extracted"] += result.get(
            "events_extracted",
            0,
        )
        counts["new_events"] += result.get(
            "new_events",
            0,
        )
        counts["existing_events_linked"] += result.get(
            "existing_events_linked",
            0,
        )
        counts["knowledge_items_extracted"] += result.get(
            "knowledge_items_extracted",
            0,
        )
        counts["new_knowledge_items"] += result.get(
            "new_knowledge_items",
            0,
        )
        counts["existing_knowledge_items_linked"] += result.get(
            "existing_knowledge_items_linked",
            0,
        )

        counts["evidence_quotes_returned"] += len(
            result.get("event_evidence", [])
        )

        embedding = result.get("embedding")

        if isinstance(embedding, dict):
            counts["embedding_chunks_created"] += embedding.get(
                "chunks_created",
                0,
            )

    return {
        "company_id": company_id,
        "company_name": company.name,
        "status": (
            "completed_with_errors"
            if counts["failed"]
            else "completed"
        ),
        "documents_considered": len(results),
        "counts": counts,
        "results": results,
    }


def get_company_ingestion_status(
    db: Session,
    company_id: str,
    include_authorized_internal: bool = False,
) -> dict[str, Any]:
    """Return counts for evidence the caller is allowed to access."""
    company = db.get(Company, company_id)

    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    visible_permissions = {"public"}
    if include_authorized_internal:
        visible_permissions.add("authorized_internal")

    sources = db.query(SourceDocument).filter(
        SourceDocument.company_id == company_id,
        SourceDocument.permission_status.in_(visible_permissions),
    ).all()
    company_events = db.query(ProductEvent.id).filter(
        ProductEvent.company_id == company_id
    ).all()
    event_ids = {row[0] for row in company_events}
    event_source_rows = []
    if event_ids:
        event_source_rows = db.execute(
            select(
                event_sources.c.event_id,
                event_sources.c.source_id,
                SourceDocument.company_id,
                SourceDocument.permission_status,
            )
            .join(
                SourceDocument,
                SourceDocument.id == event_sources.c.source_id,
            )
            .where(event_sources.c.event_id.in_(event_ids))
        ).all()

    sources_by_event: dict[str, list[tuple[str, str, str]]] = {}
    for event_id, source_id, source_company_id, permission_status in event_source_rows:
        sources_by_event.setdefault(event_id, []).append(
            (source_id, source_company_id, permission_status)
        )
    events_count = sum(
        1
        for event_id in event_ids
        if sources_by_event.get(event_id)
        and all(
            source_company_id == company_id
            and permission_status in visible_permissions
            for _, source_company_id, permission_status
            in sources_by_event[event_id]
        )
    )

    knowledge_items_count = (
        db.query(KnowledgeItem.id)
        .join(SourceDocument, SourceDocument.id == KnowledgeItem.source_id)
        .filter(
            KnowledgeItem.company_id == company_id,
            SourceDocument.company_id == company_id,
            SourceDocument.permission_status.in_(visible_permissions),
        )
        .count()
    )

    status_counts: dict[str, int] = {}

    for source in sources:
        status = source.processing_status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "company_id": company_id,
        "company_name": company.name,
        "total_sources": len(sources),
        "total_events": events_count,
        "total_knowledge_items": knowledge_items_count,
        "processing_status_counts": status_counts,
        "eligible_sources": sum(
            1 for source in sources
            if source.permission_status in ALLOWED_PERMISSION_STATUSES
        ),
    }
