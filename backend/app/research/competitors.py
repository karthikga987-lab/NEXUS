
import logging
import copy
import threading
import time
import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.intelligence.ingestion import process_company_sources
from app.models.entities import Company
from app.research.fetcher import fetch_url
from app.research.discovery import search_ddgs
from app.research.persistence import save_source
from app.research.processor import extract_page
from app.research.service import collect_company_sources


logger = logging.getLogger(__name__)

MAX_CANDIDATES = 3
MAX_PAGES_PER_COMPANY = 3
DISCOVERY_CACHE_TTL_SECONDS = 3600
DISCOVERY_CACHE_MAX_ENTRIES = 64
_DISCOVERY_CACHE: dict[str, tuple[float, dict]] = {}
_DISCOVERY_CACHE_LOCK = threading.Lock()

BLOCKED_DOMAINS = {
    "google.com",
    "bing.com",
    "duckduckgo.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "wikipedia.org",
    "reddit.com",
    "amazon.com",
    "flipkart.com",
    "pinterest.com",
    "x.com",
    "twitter.com",
}


def _search_web(query: str) -> list[dict]:
    """Use the shared bounded DDGS client for public search leads."""
    results = []
    for item in search_ddgs(query, max_results=5):
        raw_url = item.get("href") or item.get("url")
        title = item.get("title")
        if not isinstance(raw_url, str) or not isinstance(title, str):
            continue
        parsed = urlsplit(raw_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            continue

        results.append({
            "url": raw_url,
            "title": title,
        })
    return results


def _domain(url: str) -> str | None:
    try:
        hostname = urlsplit(url).hostname

        if not hostname:
            return None

        hostname = hostname.lower().strip(".")

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except (ValueError, AttributeError):
        return None


def _is_blocked_domain(domain: str) -> bool:
    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in BLOCKED_DOMAINS
    )


def _homepage(url: str) -> str | None:
    try:
        parsed = urlsplit(url)

        if not parsed.hostname:
            return None

        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            "/",
            "",
            "",
        ))

    except ValueError:
        return None


def _company_name(title: str, domain: str) -> str:
    """Derive a display name from the fetched homepage title."""

    cleaned = re.split(
        r"\s+[|]\s+|\s+[–—]\s+|\s*:\s*",
        title,
        maxsplit=1,
    )[0].strip()

    cleaned = re.sub(r"\s+", " ", cleaned)

    if len(cleaned) >= 2:
        return cleaned[:255]

    return domain.split(".")[0].replace("-", " ").title()[:255]


def _find_or_create_company(
    db: Session,
    name: str,
    website: str,
    industry: str | None,
    description: str | None,
) -> Company:
    domain = _domain(website)

    companies = db.query(Company).all()

    for company in companies:
        existing_domain = (
            _domain(company.website)
            if company.website
            else None
        )

        if domain and existing_domain == domain:
            return company

    company = Company(
        name=name,
        website=website,
        industry=industry,
        description=description,
        research_status="pending",
    )

    db.add(company)
    db.commit()
    db.refresh(company)

    return company


def discover_and_ingest_competitors(
    db: Session,
    proposal_company: Company,
    proposal_title: str,
    proposal_description: str,
    query_generator=None,
) -> dict:
    """
    Discover relevant public companies and ingest their public pages.

    Public search results are discovery leads, not verified evidence.
    Only fetched public website content is saved as source evidence.
    """

    summary = {
        "status": "completed",
        "search_query": None,
        "companies_discovered": 0,
        "companies_processed": 0,
        "sources_collected": 0,
        "sources_processed": 0,
        "sources_failed": 0,
        "sources_skipped": 0,
        "errors": [],
        "companies": [],
    }

    if not proposal_title or not proposal_title.strip():
        summary["status"] = "skipped"
        summary["errors"].append("Proposal title is empty.")
        return summary

    # Build a concise search query using the proposal title
    # and description, prioritizing title keywords.
    ignored_terms = {
        "a", "an", "and", "the", "for", "of", "to", "in",
        "on", "with", "by", "from", "at", "as", "is", "are",
        "this", "that", "these", "those", "it", "its",
        "be", "been", "being", "into", "their", "they",
        "we", "our", "you", "your", "will", "can", "could",
        "should", "would", "may", "might", "must",
        "launch", "evaluate", "evaluation", "proposal",
        "proposed", "new", "collection", "product", "products",
        "company", "companies", "solution", "solutions",
        "system", "systems", "platform", "platforms",
    }

    company_words = set(
        re.findall(r"[a-z0-9]+", proposal_company.name.lower())
    )

    keywords = []

    def add_keywords(text: str, limit: int) -> None:
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if (
                len(word) < 3
                or word in ignored_terms
                or word in company_words
                or word in keywords
            ):
                continue

            keywords.append(word)

            if len(keywords) >= limit:
                break

    add_keywords(proposal_title, 6)

    if proposal_description:
        add_keywords(proposal_description, 8)

    if not keywords and proposal_company.industry:
        add_keywords(proposal_company.industry, 8)

    if keywords:
        query = " ".join(keywords[:8]) + " brands official websites"
    elif proposal_company.industry:
        query = (
            proposal_company.industry.strip()
            + " brands official websites"
        )
    else:
        query = "product innovation brands official websites"

    summary["search_query"] = query
    cache_key = "|".join((
        str(proposal_company.id),
        proposal_title.strip().casefold(),
        " ".join((proposal_description or "").split()).casefold(),
    ))
    now = time.monotonic()
    with _DISCOVERY_CACHE_LOCK:
        cached = _DISCOVERY_CACHE.get(cache_key)
        if cached and now - cached[0] <= DISCOVERY_CACHE_TTL_SECONDS:
            response = copy.deepcopy(cached[1])
            response["discovery_cache_hit"] = True
            response["evidence_origin"] = "cached"
            response["status"] = "completed"
            return response
        if cached:
            _DISCOVERY_CACHE.pop(cache_key, None)

    queries = []
    if query_generator is not None:
        try:
            generated = query_generator(
                proposal_company.name,
                proposal_title,
                proposal_description or "",
            )
            if isinstance(generated, list):
                queries = list(dict.fromkeys(
                    " ".join(value.split())
                    for value in generated
                    if isinstance(value, str) and value.strip() and len(value) <= 200
                ))[:3]
        except Exception as exc:
            logger.warning(
                "AI proposal-query generation failed; using keyword fallback (%s).",
                type(exc).__name__,
            )
    if not queries:
        queries = [query]
    summary["search_query"] = " | ".join(queries)

    search_results = []
    failed_queries = 0
    for query_index, search_query in enumerate(queries, start=1):
        try:
            search_results.extend(_search_web(search_query) or [])
        except Exception as exc:
            failed_queries += 1
            logger.warning(
                "External search query %d failed safely (%s).",
                query_index,
                type(exc).__name__,
            )
            summary["errors"].append(
                f"Public search query {query_index} unavailable."
            )
        if len(search_results) >= MAX_CANDIDATES * 3:
            break

    if not search_results and failed_queries:
        summary["status"] = "search_failed"
        return summary

    proposing_domain = (
        _domain(proposal_company.website)
        if proposal_company.website
        else None
    )

    candidates = []
    seen_domains = set()

    for result in search_results:
        domain = _domain(result["url"])

        if not domain:
            continue

        if domain == proposing_domain:
            continue

        if _is_blocked_domain(domain):
            continue

        if domain in seen_domains:
            continue

        seen_domains.add(domain)

        homepage = _homepage(result["url"])

        if homepage:
            candidates.append(homepage)

        if len(candidates) >= MAX_CANDIDATES:
            break

    summary["companies_discovered"] = len(candidates)

    for homepage in candidates:
        domain = _domain(homepage)

        try:
            # Fetch the candidate homepage once.
            html = fetch_url(homepage)

            if not html:
                summary["errors"].append(
                    f"Could not fetch candidate website: {domain}"
                )
                continue

            page = extract_page(html, homepage)
            content = page.get("content_text") or ""
            title = page.get("title") or ""

            if len(content) < 400 or not title:
                summary["errors"].append(
                    f"Insufficient homepage content: {domain}"
                )
                continue

            name = _company_name(title, domain)

            competitor = _find_or_create_company(
                db=db,
                name=name,
                website=homepage,
                industry=None,
                description=page.get("meta_description"),
            )

            # Store the fetched homepage under its own company record.
            source, created = save_source(
                db,
                competitor.id,
                homepage,
                page,
            )

            if created:
                summary["sources_collected"] += 1

            # Reuse the fetched homepage during discovery and collection.
            collection = collect_company_sources(
                db,
                competitor.id,
                max_pages=MAX_PAGES_PER_COMPANY,
                homepage_html=html,
            )

            collection_counts = collection.get("counts", {}) or {}

            additional_sources_created = collection_counts.get(
                "created",
                0,
            )

            summary["sources_collected"] += additional_sources_created

            # Extract events and create embeddings from stored sources.
            processing = process_company_sources(
                db,
                competitor.id,
                limit=10,
                force=False,
            )

            # Read the actual nested ingestion counters.
            processing_counts = processing.get("counts", {}) or {}

            processed_count = processing_counts.get("processed", 0)
            failed_count = processing_counts.get("failed", 0)
            skipped_count = processing_counts.get("skipped", 0)

            summary["sources_processed"] += processed_count
            summary["sources_failed"] += failed_count
            summary["sources_skipped"] += skipped_count

            summary["companies_processed"] += 1

            summary["companies"].append({
                "company_id": competitor.id,
                "company_name": competitor.name,
                "website": competitor.website,
                "homepage_source_id": source.id,
                "additional_sources_collected": additional_sources_created,
                "processing_status": processing.get(
                    "status",
                    "completed",
                ),
            })

        except Exception as exc:
            logger.exception(
                "Competitor ingestion failed for %s",
                domain,
            )

            summary["errors"].append(
                f"{domain}: {str(exc)[:250]}"
            )

            # Keep processing other candidates if one site fails.
            try:
                db.rollback()
            except Exception:
                pass

    if summary["errors"]:
        summary["status"] = "completed_with_errors"
    summary["discovery_cache_hit"] = False
    summary["evidence_origin"] = "newly_collected"
    if summary["status"] in {"completed", "completed_with_errors"}:
        with _DISCOVERY_CACHE_LOCK:
            _DISCOVERY_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(summary))
            if len(_DISCOVERY_CACHE) > DISCOVERY_CACHE_MAX_ENTRIES:
                oldest_key = min(_DISCOVERY_CACHE, key=lambda key: _DISCOVERY_CACHE[key][0])
                _DISCOVERY_CACHE.pop(oldest_key, None)

    return summary
