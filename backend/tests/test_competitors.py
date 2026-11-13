
from types import SimpleNamespace
from unittest.mock import call

import pytest

from app.research import competitors


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    """Keep independent competitor-discovery tests isolated."""
    competitors._DISCOVERY_CACHE.clear()
    yield
    competitors._DISCOVERY_CACHE.clear()


def make_proposal_company():
    return SimpleNamespace(
        id="company-1",
        name="NEXUS Demo",
        website="https://nexus.example",
        industry="Technology",
    )


def prepare_successful_competitor(monkeypatch, homepage_html="homepage html"):
    """Mock the database-dependent parts of successful ingestion."""

    competitor = SimpleNamespace(
        id="competitor-1",
        name="Competitor One",
        website="https://competitor.example/",
    )

    source = SimpleNamespace(id="source-1")

    fetch_mock = monkeypatch.setattr(
        competitors,
        "fetch_url",
        lambda url: homepage_html,
    )

    monkeypatch.setattr(
        competitors,
        "extract_page",
        lambda html, url: {
            "title": "Competitor One",
            "content_text": "Product information " * 50,
            "meta_description": "Competitor product information",
        },
    )

    monkeypatch.setattr(
        competitors,
        "_find_or_create_company",
        lambda **kwargs: competitor,
    )

    monkeypatch.setattr(
        competitors,
        "save_source",
        lambda *args, **kwargs: (source, True),
    )

    collection_calls = []

    def fake_collect(*args, **kwargs):
        collection_calls.append((args, kwargs))
        return {
            "status": "completed",
            "counts": {
                "created": 2,
                "collected": 2,
                "failed": 0,
                "skipped": 0,
            },
        }

    monkeypatch.setattr(
        competitors,
        "collect_company_sources",
        fake_collect,
    )

    monkeypatch.setattr(
        competitors,
        "process_company_sources",
        lambda *args, **kwargs: {
            "status": "completed",
            "counts": {
                "processed": 3,
                "failed": 0,
                "skipped": 0,
            },
        },
    )

    return competitor, source, collection_calls


def test_search_query_uses_proposal_title_and_description(monkeypatch):
    captured_queries = []

    def fake_search(query):
        captured_queries.append(query)
        return []

    monkeypatch.setattr(
        competitors,
        "_search_web",
        fake_search,
    )

    company = make_proposal_company()

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="AI music recommendation engine",
        proposal_description=(
            "Personalized podcast discovery and audio streaming "
            "recommendations for listeners."
        ),
    )

    assert result["status"] == "completed"
    assert len(captured_queries) == 1

    query = captured_queries[0].lower()

    assert "music" in query
    assert "recommendation" in query
    assert "podcast" in query
    assert "discovery" in query
    assert "nexus" not in query


def test_search_uses_shared_ddgs_results_and_rejects_unsafe_links(monkeypatch):
    monkeypatch.setattr(
        competitors,
        "search_ddgs",
        lambda query, max_results: [
            {"href": "https://bottle.example/product", "title": "Bottle"},
            {"href": "javascript:alert(1)", "title": "Unsafe"},
            {"href": "file:///secret", "title": "Local"},
        ],
    )

    assert competitors._search_web("synthetic bottle query") == [{
        "url": "https://bottle.example/product",
        "title": "Bottle",
    }]


def test_ai_search_queries_are_bounded_and_search_failures_are_safe(monkeypatch):
    captured = []
    real_search_web = competitors._search_web
    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: (captured.append(query) or []),
    )
    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=make_proposal_company(),
        proposal_title="ThermoSmart bottle",
        proposal_description="Hypothetical temperature display.",
        query_generator=lambda *args: ["query one", "query two", "query three", "query four"],
    )
    assert captured == ["query one", "query two", "query three"]
    assert result["status"] == "completed"
    assert result["search_query"] == "query one | query two | query three"

    monkeypatch.setattr(
        competitors,
        "search_ddgs",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("DDGS search service unavailable")
        ),
    )
    monkeypatch.setattr(
        competitors,
        "_search_web",
        real_search_web,
    )
    failed = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=make_proposal_company(),
        proposal_title="Different bounded test proposal",
        proposal_description="Hypothetical temperature display.",
        query_generator=lambda *args: ["one bounded query"],
    )
    assert failed["status"] == "search_failed"
    assert failed["errors"] == ["Public search query 1 unavailable."]


def test_own_company_and_blocked_domains_are_excluded(monkeypatch):
    company = make_proposal_company()

    search_results = [
        {
            "url": "https://nexus.example/products",
            "title": "NEXUS",
        },
        {
            "url": "https://facebook.com/example",
            "title": "Facebook",
        },
        {
            "url": "https://competitor.example/products",
            "title": "Competitor",
        },
    ]

    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: search_results,
    )

    fetched_urls = []

    def fake_fetch(url):
        fetched_urls.append(url)
        return None

    monkeypatch.setattr(
        competitors,
        "fetch_url",
        fake_fetch,
    )

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="Music recommendation engine",
        proposal_description="Podcast discovery",
    )

    assert result["companies_discovered"] == 1
    assert fetched_urls == [
        "https://competitor.example/"
    ]


def test_competitor_homepage_is_fetched_only_once(monkeypatch):
    company = make_proposal_company()

    competitor, source, collection_calls = (
        prepare_successful_competitor(monkeypatch)
    )

    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: [
            {
                "url": "https://competitor.example/products",
                "title": "Competitor",
            }
        ],
    )

    fetch_calls = []

    def fake_fetch(url):
        fetch_calls.append(url)
        return "homepage html"

    monkeypatch.setattr(
        competitors,
        "fetch_url",
        fake_fetch,
    )

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="Music recommendation engine",
        proposal_description="Podcast discovery",
    )

    assert fetch_calls == [
        "https://competitor.example/"
    ]

    assert len(collection_calls) == 1

    _, collection_kwargs = collection_calls[0]

    assert collection_kwargs["homepage_html"] == "homepage html"

    assert result["companies_processed"] == 1
    assert result["sources_collected"] == 3
    assert result["companies"][0]["homepage_source_id"] == source.id


def test_existing_homepage_source_is_not_counted_as_new(monkeypatch):
    company = make_proposal_company()

    competitor, source, _ = prepare_successful_competitor(monkeypatch)

    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: [
            {
                "url": "https://competitor.example/",
                "title": "Competitor",
            }
        ],
    )

    monkeypatch.setattr(
        competitors,
        "save_source",
        lambda *args, **kwargs: (source, False),
    )

    monkeypatch.setattr(
        competitors,
        "collect_company_sources",
        lambda *args, **kwargs: {
            "status": "completed",
            "counts": {
                "created": 0,
                "collected": 1,
                "failed": 0,
                "skipped": 0,
            },
        },
    )

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="Music recommendation engine",
        proposal_description="Podcast discovery",
    )

    assert result["sources_collected"] == 0
    assert result["companies"][0]["additional_sources_collected"] == 0


def test_failed_candidate_does_not_stop_other_candidates(monkeypatch):
    company = make_proposal_company()

    competitor, source, _ = prepare_successful_competitor(monkeypatch)

    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: [
            {
                "url": "https://failed.example/",
                "title": "Failed Competitor",
            },
            {
                "url": "https://competitor.example/",
                "title": "Competitor",
            },
        ],
    )

    fetch_calls = []

    def fake_fetch(url):
        fetch_calls.append(url)

        if "failed.example" in url:
            return None

        return "homepage html"

    monkeypatch.setattr(
        competitors,
        "fetch_url",
        fake_fetch,
    )

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="Music recommendation engine",
        proposal_description="Podcast discovery",
    )

    assert len(fetch_calls) == 2
    assert result["companies_discovered"] == 2
    assert result["companies_processed"] == 1
    assert result["status"] == "completed_with_errors"
    assert len(result["errors"]) == 1


def test_company_name_parsing_handles_title_separators():
    assert competitors._company_name(
        "Spotify | Music for everyone",
        "spotify.com",
    ) == "Spotify"

    assert competitors._company_name(
        "Example – Official Website",
        "example.com",
    ) == "Example"

    assert competitors._company_name(
        "Example — Official Website",
        "example.com",
    ) == "Example"

    assert competitors._company_name(
        "Example: About Us",
        "example.com",
    ) == "Example"

def test_discovered_company_is_not_assigned_unverified_industry(monkeypatch):
    company = make_proposal_company()

    competitor, source, _ = prepare_successful_competitor(monkeypatch)

    captured_company_data = {}

    def capture_company_creation(**kwargs):
        captured_company_data.update(kwargs)
        return competitor

    monkeypatch.setattr(
        competitors,
        "_find_or_create_company",
        capture_company_creation,
    )

    monkeypatch.setattr(
        competitors,
        "_search_web",
        lambda query: [
            {
                "url": "https://competitor.example/",
                "title": "Competitor",
            }
        ],
    )

    monkeypatch.setattr(
        competitors,
        "fetch_url",
        lambda url: "homepage html",
    )

    result = competitors.discover_and_ingest_competitors(
        db=None,
        proposal_company=company,
        proposal_title="Music recommendation engine",
        proposal_description="Podcast discovery",
    )

    assert result["companies_processed"] == 1
    assert captured_company_data["industry"] is None
    assert captured_company_data["description"] == (
        "Competitor product information"
    )
