
import logging
import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.models import Company, ResearchRun
from app.research.discovery import (
    SourceDiscoveryError,
    discover_company_candidates,
    discover_sources,
)
from app.research.fetcher import fetch_url_with_diagnostics
from app.research.persistence import save_search_snippet, save_source
from app.research.processor import extract_page
from app.research.url_utils import normalize_url


logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 12
MAX_PAGES = 12
MIN_CONTENT_CHARACTERS = 800

EXCLUDED_PATH_SEGMENTS = {
    "playlist",
    "track",
    "artist",
    "album",
    "episode",
    "user",
    "collection",
    "section",
    "impressum",
    "privacy",
    "terms",
    "cookies",
    "cookie",
    "login",
    "signin",
    "signup",
    "account",
    "checkout",
    "cart",
    "careers",
    "jobs",
}

EXCLUDED_TITLE_TERMS = {
    "page not found",
    "404 not found",
    "privacy policy",
    "cookie policy",
    "terms of service",
    "terms and conditions",
    "impressum",
}

RESEARCH_TERMS = {
    "product",
    "products",
    "feature",
    "features",
    "premium",
    "pricing",
    "subscription",
    "subscriptions",
    "platform",
    "service",
    "services",
    "software",
    "technology",
    "integration",
    "integrations",
    "music",
    "podcast",
    "podcasts",
    "audiobook",
    "audiobooks",
    "streaming",
    "offline",
    "download",
    "downloads",
    "artist",
    "creator",
    "creators",
    "device",
    "devices",
    "plan",
    "plans",
    "release",
    "releases",
    "update",
    "updates",
    "launch",
    "launched",
    "business",
    "company",
    "innovation",
    "engineering",
    "dj",
}


def _same_origin(url: str, website: str) -> bool:
    """Ensure a candidate URL belongs to the registered company website."""

    try:
        candidate = urlsplit(url)
        registered = urlsplit(website)

        candidate_port = candidate.port or (
            443 if candidate.scheme.lower() == "https" else 80
        )
        registered_port = registered.port or (
            443 if registered.scheme.lower() == "https" else 80
        )

        return (
            candidate.scheme.lower() in {"http", "https"}
            and candidate.scheme.lower() == registered.scheme.lower()
            and candidate.hostname is not None
            and registered.hostname is not None
            and candidate.hostname.lower().removeprefix("www.") == registered.hostname.lower().removeprefix("www.")
            and candidate_port == registered_port
            and candidate.username is None
            and candidate.password is None
        )

    except ValueError:
        return False


def _page_quality_issue(url: str, page: dict) -> str | None:
    """
    Return a rejection reason when a page is unsuitable for research.

    This is a basic relevance heuristic. It does not establish that
    a page documents a product event or business decision.
    """

    parsed = urlsplit(url)

    path_segments = {
        segment.lower()
        for segment in parsed.path.split("/")
        if segment
    }

    excluded_segments = path_segments.intersection(
        EXCLUDED_PATH_SEGMENTS
    )

    if excluded_segments:
        return (
            "URL belongs to an excluded content category: "
            + ", ".join(sorted(excluded_segments))
        )

    title = page.get("title")
    description = page.get("meta_description")
    content = page.get("content_text")

    if not isinstance(title, str) or not title.strip():
        return "Page does not have a meaningful title."

    normalized_title = title.lower()

    if any(
        term in normalized_title
        for term in EXCLUDED_TITLE_TERMS
    ):
        return "Page title indicates legal, policy, or error content."

    if not isinstance(content, str):
        return "Page does not contain readable text."

    content = content.strip()

    if len(content) < MIN_CONTENT_CHARACTERS:
        return (
            f"Page contains too little readable text "
            f"({len(content)} characters; minimum "
            f"{MIN_CONTENT_CHARACTERS})."
        )

    searchable_text = " ".join(
        [
            title,
            description if isinstance(description, str) else "",
            content[:12000],
        ]
    ).lower()

    tokens = set(
        re.findall(r"[a-z0-9]+", searchable_text)
    )

    matching_terms = tokens.intersection(RESEARCH_TERMS)

    if len(matching_terms) < 2:
        return (
            "Page does not contain enough relevant product or "
            "company information."
        )

    return None


def collect_company_sources(
    db: Session,
    company_id: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    homepage_html: str | None = None,
    search_depth: int = 4,
    searcher=None,
    research_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Discover, fetch, extract, quality-check and persist public pages.

    This function does not run AI extraction or embedding generation.
    Newly collected or changed documents remain pending for the
    existing process_company_sources ingestion pipeline.
    """

    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("A company ID is required.")

    if not isinstance(max_pages, int) or isinstance(max_pages, bool):
        raise ValueError("max_pages must be an integer.")

    if max_pages < 1 or max_pages > MAX_PAGES:
        raise ValueError(
            f"max_pages must be between 1 and {MAX_PAGES}."
        )

    if not isinstance(search_depth, int) or isinstance(search_depth, bool) or not 1 <= search_depth <= 6:
        raise ValueError("search_depth must be between 1 and 6.")

    company = db.get(Company, company_id)

    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    if not company.website:
        raise ValueError(
            "Company does not have a website configured."
        )

    website = company.website.strip()

    started_at = datetime.now(timezone.utc)
    official_budget = min(max_pages, max(1, min(4, (max_pages + 1) // 2)))
    discovery_errors = []
    try:
        official_urls = discover_sources(
            website=website,
            max_pages=official_budget,
            homepage_html=homepage_html,
        )
    except SourceDiscoveryError as exc:
        if "homepage could not be fetched" not in str(exc).casefold():
            raise
        official_urls = []
        discovery_errors.append("Official homepage unavailable; search discovery was attempted.")

    candidates, search_errors = discover_company_candidates(
        company,
        max_pages=max_pages,
        search_depth=search_depth,
        searcher=searcher,
        official_urls=official_urls,
    )
    discovery_errors.extend(search_errors)

    results = []

    counts = {
        "discovered": len(candidates),
        "processed": 0,
        "collected": 0,
        "created": 0,
        "updated_or_unchanged": 0,
        "failed": 0,
        "skipped": 0,
        "skipped_duplicates": 0,
        "snippets_saved": 0,
        "ingestion_processed": 0,
    }

    seen: set[str] = set()
    for candidate in candidates:
        url = candidate["url"]
        normalized_url = normalize_url(url)
        if not normalized_url:
            counts["skipped"] += 1
            results.append({
                "url": url,
                "status": "skipped",
                "reason": "Discovered URL is not a valid HTTP(S) address.",
            })
            continue
        if normalized_url in seen:
            counts["skipped_duplicates"] += 1
            results.append({
                "url": url,
                "status": "skipped_duplicate",
                "reason": "Duplicate normalized URL in this research run.",
            })
            continue
        seen.add(normalized_url)
        candidate["url"] = normalized_url

        is_company_site = candidate.get("evidence_origin") == "public_company"
        if is_company_site and not _same_origin(normalized_url, website):
            counts["skipped"] += 1
            results.append({
                "url": normalized_url,
                "status": "skipped",
                "reason": (
                    "URL is outside the registered company website origin."
                ),
            })
            continue

        try:
            # Reuse homepage HTML only for the exact first official URL.
            if (
                homepage_html is not None
                and official_urls
                and url == normalize_url(official_urls[0])
            ):
                html = homepage_html
                fetch_reason = (
                    None if html else "Homepage HTML was empty."
                )
            else:
                fetch_result = fetch_url_with_diagnostics(url)
                html = fetch_result["content"]
                fetch_reason = fetch_result["reason"]

            if not html:
                counts["failed"] += 1
                failure = {
                    "url": url,
                    "status": "failed",
                    "reason": fetch_reason or "Fetch returned no HTML.",
                }
                if candidate.get("snippet"):
                    try:
                        snippet_source, snippet_created = save_search_snippet(
                            db, company_id, candidate
                        )
                        counts["snippets_saved"] += 1
                        failure["snippet_saved"] = True
                        failure["source_id"] = snippet_source.id
                        failure["snippet_created"] = snippet_created
                    except Exception:
                        db.rollback()
                        logger.warning(
                            "Could not retain discovery snippet for %s",
                            url,
                            exc_info=True,
                        )
                        failure["snippet_saved"] = False
                results.append(failure)
                continue
            page = extract_page(
                html=html,
                page_url=url,
            )

            quality_issue = _page_quality_issue(url, page)

            if quality_issue:
                counts["skipped"] += 1
                results.append({
                    "url": url,
                    "title": page.get("title"),
                    "status": "skipped",
                    "reason": quality_issue,
                })
                if candidate.get("snippet"):
                    try:
                        snippet_source, snippet_created = save_search_snippet(
                            db, company_id, candidate
                        )
                        counts["snippets_saved"] += 1
                        results[-1]["snippet_saved"] = True
                        results[-1]["source_id"] = snippet_source.id
                    except Exception:
                        db.rollback()
                        logger.warning(
                            "Could not retain low-quality-page discovery snippet",
                            exc_info=True,
                        )
                continue

            source, created = save_source(
                db=db,
                company_id=company_id,
                url=url,
                page=page,
                source_category=candidate.get("source_category") or "company_page",
                evidence_origin=candidate.get("evidence_origin") or "public_company",
                discovery_method=candidate.get("discovery_method") or "homepage_sitemap_or_same_domain_link",
                original_url=candidate.get("original_url") or url,
            )

            counts["collected"] += 1
            counts["processed"] += 1
            if source.processing_status == "processed":
                counts["ingestion_processed"] += 1

            if created:
                counts["created"] += 1
                status = "created"
            else:
                counts["updated_or_unchanged"] += 1
                status = "updated_or_unchanged"

            results.append({
                "url": url,
                "source_id": source.id,
                "title": source.title,
                "status": status,
                "processing_status": source.processing_status,
                "source_classification": candidate.get("evidence_origin"),
                "source_category": candidate.get("source_category"),
                "discovery_method": candidate.get("discovery_method"),
            })

        except Exception as exc:
            logger.exception(
                "Research collection failed for %s",
                url,
            )

            db.rollback()

            counts["failed"] += 1

            results.append({
                "url": url,
                "status": "failed",
                "reason": "Page processing failed.",
            })

    result_status = (
        "completed_with_errors"
        if counts["failed"] or discovery_errors
        else "completed"
    )
    failure_summary = "; ".join(discovery_errors)[:500] if discovery_errors else (
        f"{counts['failed']} source fetch/processing failure(s)"
        if counts["failed"] else None
    )
    if research_run_id is not None:
        run = db.get(ResearchRun, research_run_id)
        if run is None or run.company_id != company_id:
            raise ValueError("Research run does not belong to this company.")
        run.status = result_status
        run.completed_at = datetime.now(timezone.utc)
        run.counts = dict(counts)
        run.failure_summary = failure_summary
    else:
        db.add(ResearchRun(
            company_id=company_id,
            status=result_status,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            counts=dict(counts),
            failure_summary=failure_summary,
        ))
    db.commit()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "status": result_status,
        "counts": counts,
        "results": results,
        "discovery_errors": discovery_errors,
        "next_step": (
            "Process collected documents using "
            "POST /api/ingestion/companies/"
            f"{company_id}/process"
        ),
    }
