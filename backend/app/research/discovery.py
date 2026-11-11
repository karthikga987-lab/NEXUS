
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from ddgs import DDGS

from app.research.fetcher import fetch_url
from app.research.url_utils import normalize_url


MAX_SOURCES = 30

COMMON_PAGES = [
    "/about",
    "/about-us",
    "/news",
    "/blog",
    "/press",
    "/press-releases",
    "/products",
    "/technology",
    "/investors",
    "/sustainability",
]

NEWS_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "bbc.com",
    "bbc.co.uk",
    "theguardian.com",
    "techcrunch.com",
    "forbes.com",
    "apnews.com",
    "nytimes.com",
}

REGULATOR_DOMAINS = {
    "sec.gov",
    "nhtsa.gov",
    "europa.eu",
    "fca.org.uk",
}


def clean_url(url: str) -> str:
    return normalize_url(url)


def same_domain(url: str, domain: str) -> bool:
    host = urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")
    domain = domain.lower().removeprefix("www.")

    return host == domain or host.endswith("." + domain)


def classify_source(url: str, target_domain: str) -> dict:
    host = (urlparse(url).hostname or "").lower()
    host_without_www = host.removeprefix("www.")

    if same_domain(url, target_domain):
        return {
            "source_owner_type": "target_company",
            "is_target_company_official": True,
            "is_other_company_official": False,
            "source_authority_level": 1,
        }

    if (
        host_without_www in REGULATOR_DOMAINS
        or host_without_www.endswith(".gov")
        or host_without_www.endswith(".gov.in")
        or host_without_www.endswith(".gov.uk")
    ):
        return {
            "source_owner_type": "regulator",
            "is_target_company_official": False,
            "is_other_company_official": False,
            "source_authority_level": 2,
        }

    if any(
        host_without_www == domain
        or host_without_www.endswith("." + domain)
        for domain in NEWS_DOMAINS
    ):
        return {
            "source_owner_type": "news_organization",
            "is_target_company_official": False,
            "is_other_company_official": False,
            "source_authority_level": 3,
        }

    return {
        "source_owner_type": "external",
        "is_target_company_official": False,
        "is_other_company_official": False,
        "source_authority_level": 4,
    }


def make_candidate(
    url: str,
    target_domain: str,
    discovery_method: str,
    search_query: str | None = None,
) -> dict | None:
    url = clean_url(url)

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    metadata = classify_source(url, target_domain)

    return {
        "url": url,
        **metadata,
        "discovery_method": discovery_method,
        "search_query": search_query,
    }


def get_sitemap_urls(website: str) -> list[str]:
    sitemap_url = urljoin(website.rstrip("/") + "/", "sitemap.xml")
    try:
        response = fetch_url(sitemap_url)
        if not response.ok:
            print(f"Could not read sitemap: {response.error}", flush=True)
            return []

        root = ET.fromstring(response.content or "")

        return [
            element.text.strip()
            for element in root.iter()
            if element.tag.endswith("loc") and element.text
        ]

    except ET.ParseError as error:
        print(f"Could not read sitemap: {error}", flush=True)
        return []


def get_linked_pages(website: str, target_domain: str) -> list[str]:
    response = fetch_url(website)
    if not response.ok:
        print(f"Could not inspect homepage: {response.error}", flush=True)
        return []

    try:
        soup = BeautifulSoup(response.content or "", "html.parser")
        urls = []

        for link in soup.find_all("a", href=True):
            absolute_url = urljoin(response.final_url, link["href"])

            if same_domain(absolute_url, target_domain):
                urls.append(absolute_url)

        return urls

    except Exception as error:
        print(f"Could not inspect homepage links: {error}", flush=True)
        return []


def search_external_sources(company_name: str) -> list[dict]:
    queries = [
        f"{company_name} official product updates",
        f"{company_name} latest news",
        f"{company_name} government filings",
        f"{company_name} competitor partnerships",
        f"{company_name} customer reviews",
        f"{company_name} industry analysis",
    ]

    results = []

    try:
        with DDGS(timeout=20) as search:
            for query in queries:
                try:
                    search_results = search.text(
                        query,
                        max_results=4,
                        backend="auto",
                    )

                    for result in search_results:
                        url = result.get("href")

                        if url:
                            results.append({
                                "url": url,
                                "title": result.get("title"),
                                "snippet": result.get("body"),
                                "search_query": query,
                            })

                except Exception as error:
                    print(
                        f"Search failed for '{query}': {error}",
                        flush=True,
                    )

    except Exception as error:
        print(f"DDGS initialization failed: {error}", flush=True)

    return results


def discover_sources(
    website: str | None,
    company_name: str | None = None,
) -> list[dict]:
    """
    Discover target-company pages and external public sources.

    Each result contains a URL and source metadata.
    """

    candidates = []
    target_domain = ""

    if website and website.strip():
        website = website.strip()
        if not website.startswith(("http://", "https://")):
            website = "https://" + website
        website = website.rstrip("/")
        target_domain = urlparse(website).hostname or ""
        if not target_domain:
            raise ValueError("Invalid company website URL")

    # 1. Main company website
        candidates.append(
            make_candidate(website, target_domain, "website_crawl")
        )

    # 2. Common company pages
        for page in COMMON_PAGES:
            url = urljoin(website + "/", page.lstrip("/"))
            candidates.append(
                make_candidate(url, target_domain, "common_page_discovery")
            )

    # 3. Homepage links
        for url in get_linked_pages(website, target_domain):
            candidates.append(
                make_candidate(url, target_domain, "website_link")
            )

    # 4. Sitemap URLs
        for url in get_sitemap_urls(website):
            candidates.append(make_candidate(url, target_domain, "sitemap"))

    # 5. External search
    if company_name:
        for result in search_external_sources(company_name):
            candidate = make_candidate(
                    result["url"],
                    target_domain,
                    "ddgs_search",
                    result["search_query"],
                )
            if candidate:
                candidate["search_title"] = result.get("title")
                candidate["search_snippet"] = result.get("snippet")
                candidates.append(candidate)

    # Remove invalid and duplicate URLs
    unique_candidates = []
    seen = set()

    for candidate in candidates:
        if not candidate:
            continue

        url = candidate["url"]

        if url in seen:
            continue

        seen.add(url)
        unique_candidates.append(candidate)

        if len(unique_candidates) >= MAX_SOURCES:
            break

    return unique_candidates
