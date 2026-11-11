
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models import InternalSource, SourceDocument
from app.models.entities import utc_now
from app.research.url_utils import normalize_url


def calculate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_source_by_url(
    db: Session, company_id: str, url: str
) -> SourceDocument | None:
    normalized = normalize_url(url)
    if not normalized:
        return None
    return next(
        (
            source
            for source in db.query(SourceDocument).filter_by(
                company_id=company_id
            ).all()
            if normalize_url(source.url) == normalized
        ),
        None,
    )


def save_source(
    db: Session,
    company_id: str,
    url: str,
    text: str,
    source_owner_type: str = "target_company",
    is_target_company_official: bool = True,
    is_other_company_official: bool = False,
    source_authority_level: int = 1,
    discovery_method: str = "website_crawl",
    search_query: str | None = None,
    title: str | None = None,
    publisher: str | None = None,
    source_type: str = "webpage",
    content_kind: str = "full_page",
    processing_status: str = "completed",
    fetch_error: str | None = None,
) -> SourceDocument:
    url = normalize_url(url)
    if not url:
        raise ValueError("Source URL must be a valid HTTP or HTTPS URL")
    content_hash = calculate_hash(text)

    # Identify an existing source by its URL, not just its content.
    existing = find_source_by_url(db, company_id, url)

    if existing:
        if (
            content_kind == "search_snippet"
            and existing.content_kind == "full_page"
            and existing.content_text
        ):
            existing.fetch_error = fetch_error
            db.commit()
            db.refresh(existing)
            return existing
        if existing.content_hash != content_hash:
            existing.content_text = text
            existing.content_hash = content_hash
        existing.processing_status = processing_status
        existing.content_kind = content_kind
        existing.fetch_error = fetch_error
        existing.title = title or existing.title
        existing.publisher = publisher or existing.publisher
        existing.source_type = source_type

        existing.source_owner_type = source_owner_type
        existing.is_target_company_official = (
            is_target_company_official
        )
        existing.is_other_company_official = (
            is_other_company_official
        )
        existing.source_authority_level = source_authority_level
        existing.discovery_method = discovery_method
        existing.search_query = search_query or existing.search_query
        existing.updated_at = utc_now()

        db.commit()
        db.refresh(existing)

        return existing

    source = SourceDocument(
        company_id=company_id,
        url=url,
        content_text=text,
        content_hash=content_hash,
        processing_status=processing_status,
        content_kind=content_kind,
        fetch_error=fetch_error,
        source_owner_type=source_owner_type,
        is_target_company_official=is_target_company_official,
        is_other_company_official=is_other_company_official,
        source_authority_level=source_authority_level,
        discovery_method=discovery_method,
        search_query=search_query,
        title=title,
        publisher=publisher or (urlsplit(url).hostname or None),
        source_type=source_type,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return source


def save_source_failure(
    db: Session,
    company_id: str,
    url: str,
    error: str,
    **metadata,
) -> SourceDocument:
    source = find_source_by_url(db, company_id, url)
    if source:
        source.processing_status = (
            source.processing_status if source.content_text else "failed"
        )
        source.fetch_error = error
        source.updated_at = datetime.now(timezone.utc)
        for field, value in metadata.items():
            if value is not None:
                setattr(source, field, value)
    else:
        source = SourceDocument(
            company_id=company_id,
            url=normalize_url(url),
            content_text=None,
            content_hash=None,
            source_type=metadata.pop("source_type", "webpage"),
            processing_status="failed",
            content_kind="full_page",
            fetch_error=error,
            **metadata,
        )
        db.add(source)
    db.commit()
    db.refresh(source)
    return source


def save_internal_source(
    db: Session,
    company_id: str,
    source_type: str,
    content_text: str,
    title: str | None = None,
    source_url: str | None = None,
    source_identifier: str | None = None,
    author: str | None = None,
    recorded_at: datetime | None = None,
    is_synthetic: bool | None = None,
) -> tuple[InternalSource, bool]:
    if not content_text.strip():
        raise ValueError("Internal source content must not be empty")

    existing = None
    if source_identifier:
        existing = db.query(InternalSource).filter_by(
            company_id=company_id,
            source_identifier=source_identifier,
        ).first()
    elif source_url:
        normalized_source_url = normalize_url(source_url)
        existing = next(
            (
                source
                for source in db.query(InternalSource).filter_by(
                    company_id=company_id
                ).all()
                if source.source_url == source_url
                or (
                    normalized_source_url
                    and normalize_url(source.source_url or "") == normalized_source_url
                )
            ),
            None,
        )

    content_hash = calculate_hash(content_text)
    created = existing is None
    if existing:
        if existing.content_hash != content_hash:
            existing.content_text = content_text
            existing.content_hash = content_hash
        existing.source_type = source_type
        existing.title = title or existing.title
        existing.source_url = source_url or existing.source_url
        existing.author = author or existing.author
        existing.recorded_at = recorded_at or existing.recorded_at
        if is_synthetic is not None:
            existing.is_synthetic = is_synthetic
        existing.processing_status = "completed"
        existing.updated_at = utc_now()
    else:
        existing = InternalSource(
            company_id=company_id,
            source_type=source_type,
            title=title,
            content_text=content_text,
            source_url=source_url,
            source_identifier=source_identifier,
            author=author,
            recorded_at=recorded_at,
            content_hash=content_hash,
            is_synthetic=bool(is_synthetic),
            processing_status="completed",
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing, created
