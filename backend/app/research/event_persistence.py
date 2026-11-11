
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models import KnowledgeItem, ProductEvent

if TYPE_CHECKING:
    from app.research.event_extracter import EventExtractionResult


def parse_date(date_string: str | None) -> datetime | None:
    if not date_string:
        return None
    try:
        return datetime.fromisoformat(
            date_string.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def normalize_text(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def save_events(
    db: Session,
    company_id: str,
    source_id: str,
    result: EventExtractionResult,
    source_kind: str = "public",
    source_type: str = "webpage",
) -> dict:

    events_created = 0
    events_updated = 0
    knowledge_created = 0
    knowledge_updated = 0
    company_events = db.query(ProductEvent).filter_by(company_id=company_id).all()
    source_events = [
        candidate
        for candidate in company_events
        if source_id in (candidate.source_ids or [])
        or any(
            reference.get("source_id") == source_id
            for reference in (candidate.source_references or [])
        )
    ]
    source_items = (
        db.query(KnowledgeItem)
        .filter_by(company_id=company_id, source_id=source_id)
        .all()
    )

    # ------------------------------------------
    # SAVE PRODUCT EVENTS
    # ------------------------------------------

    for event in result.events:

        event_date = parse_date(event.event_date)

        existing_events = [
            candidate
            for candidate in source_events
            if normalize_text(candidate.title) == normalize_text(event.title)
            or (
                event.evidence_quote
                and candidate.evidence_quote
                and candidate.evidence_quote.strip() == event.evidence_quote.strip()
            )
        ]

        existing = None

        for candidate in existing_events:

            same_type = (
                candidate.event_type.strip().lower()
                == event.event_type.strip().lower()
            )

            same_product = (
                (candidate.product_name or "").strip().lower()
                == (event.product_name or "").strip().lower()
            )

            dates_match = (
                candidate.event_date is None
                or event_date is None
                or candidate.event_date.date() == event_date.date()
            )

            if same_type and same_product and dates_match:
                existing = candidate
                break

        if existing:

            source_references = list(existing.source_references or [])

            new_reference = {
                "source_id": source_id,
                "source_kind": source_kind,
                "source_type": source_type,
            }

            if not any(
                ref.get("source_id") == source_id
                for ref in source_references
            ):
                source_references.append(new_reference)

            existing.source_references = source_references

            source_ids = list(existing.source_ids or [])

            if source_id not in source_ids:
                source_ids.append(source_id)

            existing.source_ids = source_ids

            existing.title = event.title
            existing.product_name = event.product_name or existing.product_name
            existing.description = event.description or existing.description

            existing.event_date = event_date or existing.event_date

            existing.stated_reason = event.stated_reason or existing.stated_reason

            existing.reported_outcome = event.reported_outcome or existing.reported_outcome

            existing.actor = event.actor or existing.actor

            existing.evidence_quote = event.evidence_quote or existing.evidence_quote

            existing.event_status = event.event_status

            existing.evidence_classification = event.evidence_classification

            if event.extraction_confidence is not None:
                existing.extraction_confidence = max(
                    existing.extraction_confidence or 0.0,
                    event.extraction_confidence,
                )

            events_updated += 1

        else:

            new_event = ProductEvent(
                company_id=company_id,
                product_name=event.product_name,
                event_type=event.event_type,
                title=event.title,
                description=event.description,
                event_date=event_date,
                stated_reason=event.stated_reason,
                reported_outcome=event.reported_outcome,
                evidence_classification=event.evidence_classification,
                source_ids=[source_id],
                extraction_confidence=event.extraction_confidence,
                actor=event.actor,
                evidence_quote=event.evidence_quote,
                event_status=event.event_status,
                source_references=[
                    {
                        "source_id": source_id,
                        "source_kind": source_kind,
                        "source_type": source_type,
                    }
                ],
            )

            db.add(new_event)
            source_events.append(new_event)
            events_created += 1

    # ------------------------------------------
    # SAVE KNOWLEDGE ITEMS
    # ------------------------------------------

    for item in result.knowledge_items:

        item_date = parse_date(item.item_date)

        # Find items of the same type from the same source.
        # Do not filter by title because Gemini may word
        # the same information differently.

        existing_items = [
            candidate
            for candidate in source_items
            if candidate.item_type == item.item_type
        ]

        existing_item = None

        normalized_description = normalize_text(item.description)
        normalized_quote = item.evidence_quote.strip()

        for candidate in existing_items:

            same_description = (
                normalize_text(candidate.description)
                == normalized_description
            )

            same_quote = (
                candidate.evidence_quote.strip()
                == normalized_quote
            )

            if same_description or same_quote:
                existing_item = candidate
                break

        if existing_item:
            existing_item.title = item.title
            existing_item.description = item.description
            existing_item.actor = item.actor or existing_item.actor
            existing_item.status = item.status
            existing_item.item_date = item_date or existing_item.item_date
            existing_item.evidence_quote = item.evidence_quote
            existing_item.evidence_classification = item.evidence_classification

            if item.extraction_confidence is not None:
                existing_item.extraction_confidence = max(
                    existing_item.extraction_confidence or 0.0,
                    item.extraction_confidence,
                )

            knowledge_updated += 1

        else:

            new_item = KnowledgeItem(
                company_id=company_id,
                item_type=item.item_type,
                title=item.title,
                description=item.description,
                actor=item.actor,
                status=item.status,
                item_date=item_date,
                evidence_quote=item.evidence_quote,
                source_kind=source_kind,
                source_type=source_type,
                source_id=source_id,
                evidence_classification=item.evidence_classification,
                extraction_confidence=item.extraction_confidence,
            )

            db.add(new_item)
            source_items.append(new_item)
            knowledge_created += 1

    db.commit()

    return {
        "events_created": events_created,
        "events_updated": events_updated,
        "knowledge_items_created": knowledge_created,
        "knowledge_items_updated": knowledge_updated,
    }
