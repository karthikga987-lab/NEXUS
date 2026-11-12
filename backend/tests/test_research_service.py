from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Company, SourceDocument
from app.research import service


def _database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'research.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, factory()


def _page_html():
    body = " ".join(
        [
            "Samsung develops products, services, and business technology."
            " Product updates and features support customers across"
            " consumer and enterprise markets."
        ] * 30
    )
    return f"<html><head><title>Samsung products and services</title></head><body><main><p>{body}</p></main></body></html>"


def _no_search_results(query, max_results=5):
    """Keep source-fetching tests deterministic and offline."""
    return []


def test_successfully_fetched_html_is_extracted_and_persisted(
    tmp_path, monkeypatch
):
    engine, db = _database(tmp_path)
    try:
        company = Company(
            name="Synthetic Samsung Test",
            website="https://samsung.example",
        )
        db.add(company)
        db.commit()
        urls = ["https://samsung.example/products"]
        monkeypatch.setattr(
            service, "discover_sources", lambda **kwargs: urls
        )
        monkeypatch.setattr(
            service,
            "fetch_url_with_diagnostics",
            lambda url: {"content": _page_html(), "reason": None},
        )

        result = service.collect_company_sources(
            db, company.id, searcher=_no_search_results
        )

        assert result["counts"] == {
            "discovered": 1,
            "processed": 1,
            "collected": 1,
            "created": 1,
            "updated_or_unchanged": 0,
            "failed": 0,
            "skipped": 0,
            "skipped_duplicates": 0,
            "snippets_saved": 0,
            "ingestion_processed": 0,
        }
        assert result["results"][0]["status"] == "created"
        saved = db.query(SourceDocument).one()
        assert saved.url == urls[0]
        assert "Samsung develops products" in saved.content_text
    finally:
        db.close()
        engine.dispose()


def test_missing_html_is_failed_without_page_extraction(
    tmp_path, monkeypatch
):
    engine, db = _database(tmp_path)
    try:
        company = Company(
            name="Synthetic Samsung Test",
            website="https://samsung.example",
        )
        db.add(company)
        db.commit()
        urls = ["https://samsung.example/products"]
        monkeypatch.setattr(
            service, "discover_sources", lambda **kwargs: urls
        )
        monkeypatch.setattr(
            service,
            "fetch_url_with_diagnostics",
            lambda url: {
                "content": None,
                "reason": "Request timed out.",
            },
        )

        def unexpected_page_extraction(**kwargs):
            raise AssertionError("Page extraction must not run without HTML")

        monkeypatch.setattr(service, "extract_page", unexpected_page_extraction)
        result = service.collect_company_sources(
            db, company.id, searcher=_no_search_results
        )

        assert result["counts"]["failed"] == 1
        assert result["counts"]["collected"] == 0
        assert result["results"][0] == {
            "url": urls[0],
            "status": "failed",
            "reason": "Request timed out.",
        }
        assert db.query(SourceDocument).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_research_statuses_and_counts_reconcile(tmp_path, monkeypatch):
    engine, db = _database(tmp_path)
    try:
        company = Company(
            name="Synthetic Samsung Test",
            website="https://samsung.example",
        )
        db.add(company)
        db.commit()
        urls = [
            "https://samsung.example/products",
            "https://samsung.example/news",
            "https://unrelated.example/products",
        ]
        monkeypatch.setattr(
            service, "discover_sources", lambda **kwargs: urls
        )
        monkeypatch.setattr(
            service,
            "fetch_url_with_diagnostics",
            lambda url: (
                {"content": _page_html(), "reason": None}
                if url == urls[0]
                else {"content": None, "reason": "HTTP error (403)."}
            ),
        )

        result = service.collect_company_sources(
            db, company.id, searcher=_no_search_results
        )
        counts = result["counts"]
        statuses = [item["status"] for item in result["results"]]

        assert counts["discovered"] == len(result["results"]) == 3
        assert counts["created"] == statuses.count("created") == 1
        assert counts["updated_or_unchanged"] == statuses.count(
            "updated_or_unchanged"
        ) == 0
        assert counts["failed"] == statuses.count("failed") == 1
        assert counts["skipped"] == statuses.count("skipped") == 1
        assert counts["collected"] == 1
        assert result["results"][1]["reason"] == "HTTP error (403)."
        assert "outside" in result["results"][2]["reason"]
    finally:
        db.close()
        engine.dispose()


def test_duplicate_urls_reuse_persisted_source(tmp_path, monkeypatch):
    engine, db = _database(tmp_path)
    try:
        company = Company(
            name="Synthetic Samsung Test",
            website="https://samsung.example",
        )
        db.add(company)
        db.commit()
        url = "https://samsung.example/products"
        monkeypatch.setattr(
            service,
            "discover_sources",
            lambda **kwargs: [url, url],
        )
        monkeypatch.setattr(
            service,
            "fetch_url_with_diagnostics",
            lambda candidate: {"content": _page_html(), "reason": None},
        )

        result = service.collect_company_sources(
            db, company.id, searcher=_no_search_results
        )

        assert result["counts"]["discovered"] == 2
        assert result["counts"]["created"] == 1
        assert result["counts"]["updated_or_unchanged"] == 0
        assert result["counts"]["collected"] == 1
        assert result["counts"]["skipped_duplicates"] == 1
        assert [item["status"] for item in result["results"]] == [
            "created", "skipped_duplicate",
        ]
        assert db.query(SourceDocument).count() == 1
    finally:
        db.close()
        engine.dispose()
