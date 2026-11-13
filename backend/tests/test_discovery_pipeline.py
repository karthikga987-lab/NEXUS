from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Company
from app.research import discovery, service
from app.research.processor import extract_page
from app.models import ResearchRun, SourceDocument


def test_search_discovery_is_relevant_normalized_and_deduplicated():
    company = Company(
        name="Synthetic Northstar Labs",
        website="https://www.northstar.example",
        industry="consumer technology",
        description="Synthetic product development company",
    )
    calls = []

    def fake_search(query, max_results=5):
        calls.append(query)
        return [
            {
                "title": "Synthetic Northstar Labs product announcement",
                "href": "https://news.example/articles/northstar?utm_source=search&id=42#top",
                "body": "Synthetic Northstar Labs announced a product update.",
            },
            {
                "title": "Unrelated sports results",
                "href": "https://sports.example/results",
                "body": "A match result with no company information.",
            },
        ]

    candidates, errors = discovery.discover_company_candidates(
        company,
        max_pages=6,
        search_depth=4,
        searcher=fake_search,
        official_urls=["https://www.northstar.example/products"],
    )

    assert len(calls) == 4
    assert "consumer technology" in calls[0]
    assert errors == []
    assert [item["url"] for item in candidates] == [
        "https://northstar.example/products",
        "https://news.example/articles/northstar?id=42",
    ]
    assert candidates[1]["original_url"].endswith("#top")
    assert candidates[1]["evidence_origin"] == "external_public"
    assert candidates[1]["discovery_method"] == "ddgs"
    assert candidates[1]["snippet"].startswith("Synthetic Northstar Labs")


def test_unavailable_full_fetch_saves_snippet_as_non_evidence_lead(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'discovery.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        company = Company(
            name="Synthetic Northstar Labs",
            website="https://northstar.example",
        )
        db.add(company)
        db.commit()
        homepage = "https://northstar.example"
        external = "https://news.example/northstar-update"
        html = (
            "<html><head><title>Northstar product and company page</title></head>"
            "<body><main>" +
            "Synthetic Northstar Labs products, features, company technology "
            "and business updates. " * 35 +
            "</main></body></html>"
        )
        monkeypatch.setattr(service, "discover_sources", lambda **kwargs: [homepage])
        monkeypatch.setattr(
            service,
            "fetch_url_with_diagnostics",
            lambda url: (
                {"content": html, "reason": None}
                if url == homepage
                else {"content": None, "reason": "Robots policy denied access."}
            ),
        )

        def fake_search(query, max_results=5):
            return [{
                "title": "Synthetic Northstar Labs update",
                "href": external,
                "body": "Synthetic snippet about a Northstar product update.",
            }]

        result = service.collect_company_sources(
            db,
            company.id,
            max_pages=3,
            search_depth=1,
            searcher=fake_search,
        )
        assert result["counts"]["discovered"] == 2
        assert result["counts"]["collected"] == 1
        assert result["counts"]["processed"] == 1
        assert result["counts"]["failed"] == 1
        assert result["counts"]["snippets_saved"] == 1
        failed = next(item for item in result["results"] if item["status"] == "failed")
        assert failed["snippet_saved"] is True
        snippet = db.query(SourceDocument).filter_by(url=external).one()
        assert snippet.processing_status == "skipped"
        assert snippet.source_metadata["content_kind"] == "search_snippet"
        assert snippet.source_metadata["evidence_classification"] == "unknown"
        assert "synthetic snippet" in snippet.content_text.casefold()
        assert db.query(ResearchRun).one().counts == result["counts"]
    finally:
        db.close()
        engine.dispose()


def test_html_processing_removes_cookie_boilerplate_and_reads_publication_date():
    page = extract_page(
        "<html><head><meta property='article:published_time' "
        "content='2024-05-10T12:00:00Z'><title>Synthetic release</title></head>"
        "<body><div class='cookie-consent'><div>Reject cookies</div></div>"
        "<main><p>Synthetic product release information.</p></main></body></html>",
        "https://publisher.example/story",
    )
    assert "Reject cookies" not in page["content_text"]
    assert "Synthetic product release" in page["content_text"]
    assert page["publication_date"].isoformat() == "2024-05-10T12:00:00+00:00"


def test_invalid_unicode_and_credentials_are_rejected_by_url_normalizer():
    assert discovery.normalize_url("https://user:secret@example.com/path") == ""
    assert discovery.normalize_url("https://\ud800.example/path") == ""


def test_ddgs_adapter_uses_bounded_text_search(monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = {}

    class FakeDDGS:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results):
            calls.update({"query": query, "max_results": max_results})
            return [{"href": "https://news.example/item", "title": "Synthetic"}]

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    results = discovery.search_ddgs("Synthetic company update", max_results=3)
    assert calls == {
        "timeout": 8,
        "query": "Synthetic company update",
        "max_results": 3,
    }
    assert results[0]["href"] == "https://news.example/item"
