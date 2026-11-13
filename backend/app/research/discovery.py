
import logging
import re
import xml.etree.ElementTree as ET

from html.parser import HTMLParser
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

from app.research.fetcher import fetch_url
from app.research.url_utils import normalize_url


logger = logging.getLogger(__name__)

MAX_SITEMAPS = 5
MAX_SITEMAP_URLS = 500

ROBOTS_CONTENT_TYPES = {
    "text/plain",
    "text/html",
}

SITEMAP_CONTENT_TYPES = {
    "application/xml",
    "text/xml",
    "application/xhtml+xml",
}

RELEVANT_TERMS = {
    "product": 15,
    "products": 15,
    "feature": 14,
    "features": 14,
    "pricing": 14,
    "premium": 10,
    "plan": 8,
    "plans": 8,
    "news": 12,
    "newsroom": 15,
    "press": 12,
    "blog": 9,
    "update": 12,
    "updates": 12,
    "changelog": 15,
    "release": 12,
    "releases": 12,
    "about": 7,
    "company": 7,
    "technology": 9,
    "platform": 10,
    "investor": 7,
    "innovation": 9,
    "business": 8,
    "engineering": 8,
}

IRRELEVANT_TERMS = {
    "login",
    "section",
    "signin",
    "signup",
    "register",
    "account",
    "checkout",
    "cart",
    "privacy",
    "terms",
    "cookie",
    "cookies",
    "support",
    "help",
    "contact",
    "careers",
    "jobs",
    "download",
    "playlist",
    "track",
    "artist",
    "album",
    "episode",
    "user",
    "collection",
    "browse",
    "genre",
    "mood",
    "station",
    "radio",
    "search",
}

IGNORED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".pdf",
    ".zip",
    ".mp3",
    ".mp4",
    ".woff",
    ".woff2",
    ".ttf",
}

SITEMAP_EXTENSIONS = {
    ".xml",
    ".xml.gz",
}


class SourceDiscoveryError(ValueError):
    """Raised when a company website cannot be used for discovery."""


class HomepageLinkParser(HTMLParser):
    """Extract links from homepage HTML."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")

        if href:
            self.links.append(href)


def _normalize_website(website: str) -> str:
    """Normalize a company website to its HTTP(S) origin."""

    if not isinstance(website, str) or not website.strip():
        raise SourceDiscoveryError("A company website is required.")

    value = website.strip()

    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        scheme = parsed.scheme.lower()

        if scheme not in {"http", "https"}:
            raise SourceDiscoveryError(
                "Company website must use HTTP or HTTPS."
            )

        if not hostname:
            raise SourceDiscoveryError(
                "Company website must contain a valid hostname."
            )

        if parsed.username or parsed.password:
            raise SourceDiscoveryError(
                "Company website must not contain login credentials."
            )

        port = parsed.port

        netloc = hostname.encode("idna").decode("ascii").lower()

        if ":" in netloc and not netloc.startswith("["):
            netloc = f"[{netloc}]"

        if port is not None:
            netloc = f"{netloc}:{port}"

        return urlunsplit((scheme, netloc, "/", "", ""))

    except SourceDiscoveryError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise SourceDiscoveryError(
            "Company website URL is invalid."
        ) from exc


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    port = parsed.port or (443 if scheme == "https" else 80)

    return scheme, hostname, port


def _is_same_origin(url: str, base_url: str) -> bool:
    try:
        return _origin(url) == _origin(base_url)
    except (ValueError, UnicodeError):
        return False


def _path_is_irrelevant(path: str) -> bool:
    """Reject personalized, transactional, and non-research routes."""

    segments = {
        segment.lower()
        for segment in path.split("/")
        if segment
    }

    return bool(segments.intersection(IRRELEVANT_TERMS))


def _normalize_candidate(
    url: str,
    base_url: str,
    allow_sitemap: bool = False,
) -> str | None:
    """Normalize and validate a discovered URL."""

    if not isinstance(url, str) or not url.strip():
        return None

    value = url.strip()

    if value.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None

    absolute_url = urljoin(base_url, value)

    try:
        parsed = urlsplit(absolute_url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        if not parsed.hostname or parsed.username or parsed.password:
            return None

        if not _is_same_origin(absolute_url, base_url):
            return None

        path = parsed.path.lower()

        if _path_is_irrelevant(path):
            return None

        if allow_sitemap and any(
            path.endswith(extension)
            for extension in SITEMAP_EXTENSIONS
        ):
            pass
        elif any(
            path.endswith(extension)
            for extension in IGNORED_EXTENSIONS | SITEMAP_EXTENSIONS
        ):
            return None

        tracking_names = {
            "fbclid",
            "gclid",
            "ref",
            "source",
        }

        query_items = [
            (key, query_value)
            for key, query_value in parse_qsl(
                parsed.query,
                keep_blank_values=False,
            )
            if key.lower() not in tracking_names
            and not key.lower().startswith("utm_")
        ]

        normalized_query = urlencode(query_items, doseq=True)

        normalized = urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path or "/",
                normalized_query,
                "",
            )
        )

        return normalized.rstrip("/") or normalized

    except (ValueError, UnicodeError):
        return None


def _relevance_score(url: str) -> int:
    """Rank pages by likely product and company research value."""

    path = urlsplit(url).path.lower()
    tokens = set(re.findall(r"[a-z0-9]+", path))

    score = 0

    for term, weight in RELEVANT_TERMS.items():
        if term in tokens:
            score += weight

    for term in IRRELEVANT_TERMS:
        if term in tokens:
            score -= 20

    return score


def _extract_sitemap_locations(
    xml_content: str,
) -> tuple[list[str], bool]:
    """Extract URLs from a sitemap or sitemap index."""

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        logger.warning("Could not parse sitemap XML.")
        return [], False

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    is_sitemap_index = root_name == "sitemapindex"

    locations = []

    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "loc":
            if element.text and element.text.strip():
                locations.append(element.text.strip())

        if len(locations) >= MAX_SITEMAP_URLS:
            break

    return locations, is_sitemap_index


def _discover_sitemap_urls(base_url: str) -> list[str]:
    """Find sitemap files through robots.txt and common locations."""

    parsed = urlsplit(base_url)
    root_url = f"{parsed.scheme}://{parsed.netloc}/"

    sitemap_candidates = []

    robots_url = urljoin(root_url, "robots.txt")
    robots_content = fetch_url(
        robots_url,
        allowed_content_types=ROBOTS_CONTENT_TYPES,
    )

    if robots_content:
        for line in robots_content.splitlines():
            key, separator, value = line.partition(":")

            if separator and key.strip().lower() == "sitemap":
                sitemap_candidates.append(value.strip())

    sitemap_candidates.extend([
        urljoin(root_url, "sitemap.xml"),
        urljoin(root_url, "sitemap_index.xml"),
        urljoin(root_url, "sitemap-index.xml"),
    ])

    normalized_candidates = []

    for candidate in sitemap_candidates:
        normalized = _normalize_candidate(
            candidate,
            base_url,
            allow_sitemap=True,
        )

        if normalized and normalized not in normalized_candidates:
            normalized_candidates.append(normalized)

    discovered_urls = []
    visited_sitemaps = set()
    sitemap_count = 0
    index = 0

    while index < len(normalized_candidates):
        if sitemap_count >= MAX_SITEMAPS:
            break

        sitemap_url = normalized_candidates[index]
        index += 1

        if sitemap_url in visited_sitemaps:
            continue

        visited_sitemaps.add(sitemap_url)

        xml_content = fetch_url(
            sitemap_url,
            allowed_content_types=SITEMAP_CONTENT_TYPES,
        )

        if not xml_content:
            continue

        sitemap_count += 1

        locations, is_sitemap_index = _extract_sitemap_locations(
            xml_content
        )

        for location in locations:
            if is_sitemap_index:
                normalized = _normalize_candidate(
                    location,
                    base_url,
                    allow_sitemap=True,
                )

                if (
                    normalized
                    and normalized not in visited_sitemaps
                    and normalized not in normalized_candidates
                ):
                    normalized_candidates.append(normalized)

            else:
                normalized = _normalize_candidate(
                    location,
                    base_url,
                )

                if normalized and normalized not in discovered_urls:
                    discovered_urls.append(normalized)

            if len(discovered_urls) >= MAX_SITEMAP_URLS:
                break

    return discovered_urls


def _discover_homepage_links(
    homepage_html: str,
    base_url: str,
) -> list[str]:
    """Extract relevant same-origin links from homepage HTML."""

    parser = HomepageLinkParser()

    try:
        parser.feed(homepage_html)
    except Exception:
        logger.warning("Could not completely parse homepage links.")

    discovered = []

    for href in parser.links:
        normalized = _normalize_candidate(href, base_url)

        if normalized and normalized not in discovered:
            discovered.append(normalized)

    return discovered


def discover_sources(
    website: str,
    max_pages: int = 12,
    homepage_html: str | None = None,
) -> list[str]:
    """
    Discover public company webpages.

    The homepage is first, followed by relevant sitemap and
    homepage links. Only same-origin URLs are returned.
    """

    if not isinstance(max_pages, int) or isinstance(max_pages, bool):
        raise ValueError("max_pages must be an integer.")

    if max_pages < 1:
        raise ValueError("max_pages must be at least 1.")

    base_url = _normalize_website(website)
    homepage = base_url.rstrip("/")

    if homepage_html is None:
        homepage_html = fetch_url(homepage)

    if not homepage_html:
         raise SourceDiscoveryError(
             "The company homepage could not be fetched as valid HTML."
    )

    sitemap_urls = _discover_sitemap_urls(base_url)

    homepage_links = _discover_homepage_links(
        homepage_html,
        base_url,
    )

    combined = []
    seen = {homepage}

    for url in sitemap_urls + homepage_links:
        if url not in seen:
            seen.add(url)
            combined.append(url)

    combined.sort(
        key=lambda url: (
            _relevance_score(url),
            len(urlsplit(url).path),
        ),
        reverse=True,
    )

    return [homepage] + combined[: max_pages - 1]


SEARCH_CATEGORIES = (
    ("product_updates", 'product launch update feature announcement'),
    ("press_release", 'official press release product'),
    ("product_pages", 'product pages product portfolio'),
    ("company_news", 'newsroom company product news'),
    ("regulatory_filing", 'annual report regulatory filing products'),
    ("industry_reporting", 'product announcement industry reporting'),
)


def _company_search_queries(company, search_depth: int) -> list[tuple[str, str]]:
    name = " ".join(str(getattr(company, "name", "") or "").split())
    if not name:
        return []
    extra = []
    industry = getattr(company, "industry", None)
    description = getattr(company, "description", None)
    if isinstance(industry, str) and industry.strip():
        extra.append(industry.strip()[:80])
    if isinstance(description, str) and description.strip():
        words = re.findall(r"[A-Za-z0-9-]+", description)[:8]
        extra.extend(words)
    context = " ".join(dict.fromkeys(extra))
    queries = []
    for category, terms in SEARCH_CATEGORIES[:search_depth]:
        query = f'"{name}" {terms}'
        if context:
            query += f" {context}"
        queries.append((category, query))
    return queries


def search_ddgs(query: str, max_results: int = 5) -> list[dict]:
    """Run one bounded DDGS query. Missing dependency/network is non-fatal."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        logger.info("DDGS is unavailable; using official-site discovery only.")
        raise RuntimeError("DDGS dependency is unavailable") from exc
    try:
        with DDGS(timeout=8) as client:
            return list(client.text(query, max_results=max_results) or [])
    except Exception as exc:
        logger.warning("DDGS search failed safely: %s", type(exc).__name__)
        raise RuntimeError("DDGS search service unavailable") from exc


def _candidate_origin(url: str, company_website: str) -> str:
    try:
        source_host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
        company_host = (urlsplit(_normalize_website(company_website)).hostname or "").casefold().removeprefix("www.")
    except (ValueError, UnicodeError):
        return "external_public"
    if source_host == company_host or source_host.endswith("." + company_host):
        return "public_company"
    return "external_public"


def _matches_company(company, result: dict, url: str) -> bool:
    name = " ".join(str(getattr(company, "name", "") or "").split()).casefold()
    text = " ".join(str(result.get(key) or "") for key in ("title", "body", "snippet")).casefold()
    host = (urlsplit(url).hostname or "").casefold()
    if not name:
        return False
    if name in text:
        return True
    name_tokens = [token for token in re.findall(r"[a-z0-9]+", name) if len(token) > 2]
    matching = sum(token in text for token in name_tokens)
    company_host = (urlsplit(getattr(company, "website", "") or "").hostname or "").casefold()
    if company_host and (host == company_host or host.endswith("." + company_host)):
        return True
    return bool(name_tokens) and matching >= max(1, (len(name_tokens) + 1) // 2)


def discover_company_candidates(
    company,
    *,
    max_pages: int = 12,
    search_depth: int = 4,
    searcher=None,
    official_urls: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Combine official-site discovery with bounded, attributed DDGS leads.

    Search snippets are retained only as discovery metadata. The research
    service must fetch and parse the URL before counting it as collected.
    """
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 12:
        raise ValueError("max_pages must be between 1 and 12.")
    if not isinstance(search_depth, int) or isinstance(search_depth, bool) or not 1 <= search_depth <= 6:
        raise ValueError("search_depth must be between 1 and 6.")
    website = getattr(company, "website", None)
    if not website:
        raise SourceDiscoveryError("A company website is required.")

    # Reserve room for public reporting while retaining official homepage and
    # highest-ranked same-domain pages. If DDGS is unavailable, this remains
    # a useful official-only discovery result.
    if official_urls is None:
        official_budget = min(max_pages, max(1, min(4, (max_pages + 1) // 2)))
        official_urls = discover_sources(website, max_pages=official_budget)
    candidates: list[dict] = []
    seen: set[str] = set()
    for url in official_urls:
        normalized = normalize_url(url)
        if not normalized:
            continue
        if normalized in seen:
            candidates.append({
                "url": normalized,
                "original_url": url,
                "title": None,
                "snippet": None,
                "source_category": "company_page",
                "discovery_method": "homepage_sitemap_or_same_domain_link",
                "evidence_origin": "public_company",
            })
            continue
        seen.add(normalized)
        candidates.append({
            "url": normalized,
            "original_url": url,
            "title": None,
            "snippet": None,
            "source_category": "company_page",
            "discovery_method": "homepage_sitemap_or_same_domain_link",
            "evidence_origin": "public_company",
        })

    errors: list[str] = []
    run_search = searcher or search_ddgs
    for category, query in _company_search_queries(company, search_depth):
        if len(candidates) >= max_pages:
            break
        try:
            results = run_search(query, max_results=min(5, max_pages)) or []
        except Exception as exc:
            logger.warning("DDGS query failed safely: %s", type(exc).__name__)
            errors.append(f"{category}: search unavailable")
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            raw_url = result.get("href") or result.get("url")
            url = normalize_url(raw_url) if isinstance(raw_url, str) else ""
            if not url:
                continue
            if url in seen:
                continue
            if not _matches_company(company, result, url):
                continue
            seen.add(url)
            candidates.append({
                "url": url,
                "original_url": raw_url,
                "title": str(result.get("title") or "")[:500] or None,
                "snippet": str(result.get("body") or result.get("snippet") or "")[:2000] or None,
                "source_category": category,
                "discovery_method": "ddgs",
                "evidence_origin": _candidate_origin(url, website),
            })
            if len(candidates) >= max_pages:
                break
    return candidates, errors
