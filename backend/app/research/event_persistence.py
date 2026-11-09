from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ProductEvent
from app.research.event_extracter import ExtractedEvent


def parse_event_date(date_string: str | None) -> datetime | None:
    """Convert an ISO date string into a Python datetime."""

    if not date_string:
        return None

    try:
        return datetime.fromisoformat(
            date_string.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def save_events(
    db: Session,
    company_id: str,
    source_id: str,
    events: list[ExtractedEvent],
) -> dict:

    created = 0
    updated = 0

    for event in events:

        event_date = parse_event_date(event.event_date)

        # Find events with the same title for this company
        existing_events = (
            db.query(ProductEvent)
            .filter(
                ProductEvent.company_id == company_id,
                ProductEvent.title.ilike(event.title.strip()),
            )
            .all()
        )

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

            # Attach another source to the existing event
            source_ids = list(existing.source_ids or [])

            if source_id not in source_ids:
                source_ids.append(source_id)

            existing.source_ids = source_ids

            # Fill missing information without overwriting known details
            if not existing.description:
                existing.description = event.description

            if not existing.event_date:
                existing.event_date = event_date

            if not existing.stated_reason:
                existing.stated_reason = event.stated_reason

            if not existing.reported_outcome:
                existing.reported_outcome = event.reported_outcome

            if existing.evidence_classification == "unknown":
                existing.evidence_classification = (
                    event.evidence_classification
                )

            if event.extraction_confidence is not None:
                existing.extraction_confidence = max(
                    existing.extraction_confidence or 0.0,
                    event.extraction_confidence,
                )

            updated += 1

        else:

            # Create a new database event
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
            )

            db.add(new_event)
            created += 1

    db.commit()

    return {
        "events_created": created,
        "events_updated": updated,
    }
