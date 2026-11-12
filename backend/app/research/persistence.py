import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from sqlalchemy.orm import Session

from app.models import Company, SourceDocument


logger = logging.getLogger(__name__)


class SourcePersistenceError(ValueError):
    """Raised when a webpage cannot be saved as a source document."""


def calculate_hash(text: str) -> str:
    """Calculate a stable SHA-256 hash of normalized webpage text."""

    normalized = " ".join(text.split())

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _validate_source_url(url: str) -> str:
    """Validate and normalize the source URL."""

    if not isinstance(url, str) or not url.strip():
        raise SourcePersistenceError("A source URL is required.")

    try:
        parsed = urlsplit(url.strip())

        if parsed.scheme.lower() not in {"http", "https"}:
            raise SourcePersistenceError(
                "Source URL must use HTTP or HTTPS."
            )

        if not parsed.hostname:
            raise SourcePersistenceError(
                "Source URL must contain a hostname."
            )

        if parsed.username or parsed.password:
            raise SourcePersistenceError(
                "Source URL must not contain login credentials."
            )

        return url.strip()

    except SourcePersistenceError:
        raise
    except ValueError as exc:
        raise SourcePersistenceError(
            "Source URL is invalid."
        ) from exc


def save_source(
    db: Session,
    company_id: str,
    url: str,
    page: dict,
    *,
    source_category: str = "company_page",
    evidence_origin: str = "public_company",
    discovery_method: str = "homepage_sitemap_or_same_domain_link",
    original_url: str | None = None,
) -> tuple[SourceDocument, bool]:
    """
    Persist one collected webpage.

    Returns:
        (source_document, created_new_record)

    Deduplication is based on company ID and original URL.
    Different URLs are retained separately to preserve provenance.
    """

    if not isinstance(company_id, str) or not company_id.strip():
        raise SourcePersistenceError("A company ID is required.")

    if not isinstance(page, dict):
        raise SourcePersistenceError("Page data must be a dictionary.")

    source_url = _validate_source_url(url)

    content_text = page.get("content_text")

    if not isinstance(content_text, str) or not content_text.strip():
        raise SourcePersistenceError(
            "Webpage does not contain usable text."
        )

    company = db.get(Company, company_id)

    if company is None:
        raise SourcePersistenceError(
            f"Company not found: {company_id}"
        )

    title = page.get("title")
    if not isinstance(title, str) or not title.strip():
        title = None
    else:
        title = title.strip()[:500]

    meta_description = page.get("meta_description")
    if not isinstance(meta_description, str):
        meta_description = None

    canonical_url = page.get("canonical_url")
    if not isinstance(canonical_url, str):
        canonical_url = None

    parsed_url = urlsplit(source_url)
    publisher = parsed_url.hostname

    content_hash = calculate_hash(content_text)

    existing = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company_id,
            SourceDocument.url == source_url,
        )
        .first()
    )

    now = datetime.now(timezone.utc)

    metadata_updates = {
        "canonical_url": canonical_url,
        "meta_description": meta_description,
        "last_fetched_at": now.isoformat(),
        "content_kind": "full_document",
        "source_category": source_category,
        "discovery_method": discovery_method,
        "evidence_origin": evidence_origin,
        "evidence_classification": "unknown",
        "original_url": original_url or source_url,
        "normalized_source_url": source_url,
    }

    if existing is not None:
        old_hash = existing.content_hash

        existing.title = title or existing.title
        existing.publisher = page.get("publisher") or publisher
        existing.content_text = content_text
        existing.content_hash = content_hash
        existing.source_type = source_category or existing.source_type
        if page.get("publication_date") is not None:
            existing.publication_date = page["publication_date"]

        metadata = existing.source_metadata
        if not isinstance(metadata, dict):
            metadata = {}

        metadata = dict(metadata)
        metadata.update(metadata_updates)
        existing.source_metadata = metadata

        # Reprocess only when the actual page content has changed.
        if old_hash != content_hash:
            existing.processing_status = "pending"

        try:
            db.commit()
            db.refresh(existing)
        except Exception:
            db.rollback()
            logger.exception(
                "Could not update source document %s",
                existing.id,
            )
            raise

        return existing, False

    source = SourceDocument(
        company_id=company_id,
        url=source_url,
        title=title,
        publisher=page.get("publisher") or publisher,
        source_type=source_category or "other",
        publication_date=page.get("publication_date"),
        content_text=content_text,
        content_hash=content_hash,
        permission_status="public",
        processing_status="pending",
        source_metadata=metadata_updates,
    )

    db.add(source)

    try:
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        logger.exception(
            "Could not save source document for company %s",
            company_id,
        )
        raise

    return source, True


def save_search_snippet(
    db: Session,
    company_id: str,
    candidate: dict,
) -> tuple[SourceDocument, bool]:
    """Persist a search result as a lead, never as a collected document."""
    source_url = _validate_source_url(candidate.get("url"))
    snippet = candidate.get("snippet")
    if not isinstance(snippet, str) or not snippet.strip():
        raise SourcePersistenceError("Search result has no usable snippet.")
    company = db.get(Company, company_id)
    if company is None:
        raise SourcePersistenceError(f"Company not found: {company_id}")
    now = datetime.now(timezone.utc)
    host = urlsplit(source_url).hostname
    content = snippet.strip()[:2000]
    metadata = {
        "content_kind": "search_snippet",
        "source_category": candidate.get("source_category") or "other",
        "discovery_method": candidate.get("discovery_method") or "ddgs",
        "evidence_origin": candidate.get("evidence_origin") or "external_public",
        "search_snippet": True,
        "last_fetched_at": now.isoformat(),
        "original_url": candidate.get("original_url") or source_url,
        "normalized_source_url": source_url,
        "evidence_classification": "unknown",
    }
    existing = db.query(SourceDocument).filter(
        SourceDocument.company_id == company_id,
        SourceDocument.url == source_url,
        SourceDocument.permission_status == "public",
    ).first()
    existing_metadata = (
        existing.source_metadata
        if existing is not None and isinstance(existing.source_metadata, dict)
        else {}
    )
    if existing is not None and existing_metadata.get("content_kind") != "search_snippet":
        return existing, False
    if existing is not None:
        existing.title = candidate.get("title") or existing.title
        existing.publisher = host
        existing.source_type = str(candidate.get("source_category") or "other")[:80]
        existing.content_text = content
        existing.content_hash = calculate_hash(content)
        existing.source_metadata = {
            **existing_metadata,
            **metadata,
        }
        existing.processing_status = "skipped"
        source = existing
        created = False
    else:
        source = SourceDocument(
            company_id=company_id,
            url=source_url,
            title=(candidate.get("title") or "Search result snippet")[:500],
            publisher=host,
            source_type=str(candidate.get("source_category") or "other")[:80],
            content_text=content,
            content_hash=calculate_hash(content),
            permission_status="public",
            processing_status="skipped",
            source_metadata=metadata,
        )
        db.add(source)
        created = True
    try:
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        logger.exception("Could not persist search result metadata")
        raise
    return source, created


def save_internal_source(
    db: Session,
    company_id: str,
    original_filename: str,
    content_text: str,
    *,
    source_identifier: str | None = None,
    author: str | None = None,
    recorded_at: datetime | None = None,
    is_synthetic: bool = False,
) -> tuple[SourceDocument, bool, bool]:
    """Upsert authorized local text into the unified source pipeline."""
    if not isinstance(company_id, str) or not company_id.strip():
        raise SourcePersistenceError("A company ID is required.")
    if not isinstance(original_filename, str) or not original_filename.strip():
        raise SourcePersistenceError("An original filename is required.")
    if not isinstance(content_text, str) or not content_text.strip():
        raise SourcePersistenceError("The imported document is empty.")

    safe_name = original_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not safe_name:
        raise SourcePersistenceError("The original filename is invalid.")

    company = db.get(Company, company_id)
    if company is None:
        raise SourcePersistenceError(f"Company not found: {company_id}")

    stable_identifier = (source_identifier or safe_name).strip()
    if not stable_identifier:
        stable_identifier = safe_name

    encoded_identifier = quote(stable_identifier, safe="")[:700]
    source_url = f"internal://{company_id}/{encoded_identifier}"
    content_for_storage = content_text.strip()
    if is_synthetic and not content_for_storage.startswith(
        "[SYNTHETIC DEMO"
    ):
        content_for_storage = (
            "[SYNTHETIC DEMO — HYPOTHETICAL CONTENT]\n\n"
            + content_for_storage
        )
    content_hash = calculate_hash(content_for_storage)

    existing = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company_id,
            SourceDocument.url == source_url,
            SourceDocument.permission_status == "authorized_internal",
        )
        .first()
    )

    collected_at = datetime.now(timezone.utc)
    metadata = {
        "source_owner_type": "authorized_internal",
        "evidence_origin": (
            "synthetic_demo" if is_synthetic else "authorized_internal"
        ),
        "content_kind": "internal_document",
        "original_filename": safe_name,
        "source_identifier": stable_identifier,
        "is_synthetic": bool(is_synthetic),
        "author": author.strip()[:255] if author and author.strip() else None,
        "recorded_at": recorded_at.isoformat() if recorded_at else None,
        "last_fetched_at": collected_at.isoformat(),
    }

    if existing is not None:
        unchanged = existing.content_hash == content_hash
        existing.title = (
            f"[SYNTHETIC DEMO] {safe_name}" if is_synthetic else safe_name
        )[:500]
        existing.publisher = metadata["author"]
        existing.source_type = "internal_document"
        existing.content_text = content_for_storage
        existing.content_hash = content_hash
        existing.reliability = None
        old_metadata = existing.source_metadata
        existing.source_metadata = {
            **(old_metadata if isinstance(old_metadata, dict) else {}),
            **metadata,
        }
        if not unchanged:
            existing.processing_status = "pending"
        try:
            db.commit()
            db.refresh(existing)
        except Exception:
            db.rollback()
            logger.exception(
                "Could not update internal source for company %s",
                company_id,
            )
            raise
        return existing, False, unchanged

    source = SourceDocument(
        company_id=company_id,
        url=source_url,
        title=(
            f"[SYNTHETIC DEMO] {safe_name}"
            if is_synthetic
            else safe_name
        )[:500],
        publisher=metadata["author"],
        source_type="internal_document",
        collected_at=collected_at,
        content_text=content_for_storage,
        content_hash=content_hash,
        permission_status="authorized_internal",
        reliability=None,
        processing_status="pending",
        source_metadata=metadata,
    )
    db.add(source)
    try:
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        logger.exception(
            "Could not save internal source for company %s",
            company_id,
        )
        raise
    return source, True, False
