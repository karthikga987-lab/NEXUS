import hashlib

from sqlalchemy.orm import Session

from app.models import SourceDocument


def calculate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_source(
    db: Session,
    company_id: str,
    url: str,
    text: str,
) -> SourceDocument:

    content_hash = calculate_hash(text)

    existing = (
        db.query(SourceDocument)
        .filter_by(
            company_id=company_id,
            content_hash=content_hash,
        )
        .first()
    )

    if existing:
        return existing

    source = SourceDocument(
        company_id=company_id,
        url=url,
        content_text=text,
        content_hash=content_hash,
        source_type="webpage",
        processing_status="completed",
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return source