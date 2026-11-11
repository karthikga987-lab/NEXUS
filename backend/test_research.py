import unittest
from unittest.mock import patch
from types import SimpleNamespace
import requests

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import companies as company_routes
from app.api.routes.companies import (
    EventRelationshipCreate,
    InternalSourceCreate,
)
from app.db.session import Base
from app.models import Company, ProductEvent, SourceDocument, KnowledgeItem
from app.research.event_extracter import (
    EventExtractionResult,
    ExtractedEvent,
    ExtractedKnowledgeItem,
    _has_source_quote,
)
from app.research.event_persistence import parse_date, save_events
from app.research.fetcher import FetchResult, fetch_url
from app.research.discovery import classify_source, make_candidate
from app.research.persistence import save_internal_source, save_source
from app.research.processor import process_html
from app.schemas.contracts import CompanyCreate


class ResearchDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.company = Company(name="Example", website="https://example.com")
        self.db.add(self.company)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_research_twice_normalizes_url_and_preserves_existing_record(self):
        first = save_source(
            self.db, self.company.id,
            "https://www.example.com/news/?utm_source=search#top", "Original",
        )
        second = save_source(
            self.db, self.company.id,
            "https://example.com/news", "Original",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(1, self.db.query(SourceDocument).count())
        self.assertEqual("https://example.com/news", second.url)

    def test_changed_content_updates_existing_source(self):
        source = save_source(self.db, self.company.id, "https://example.com/a", "Old")
        source_id = source.id
        updated = save_source(self.db, self.company.id, "https://example.com/a", "New")
        self.assertEqual(source_id, updated.id)
        self.assertEqual("New", updated.content_text)
        self.assertEqual(1, self.db.query(SourceDocument).count())

    def test_same_extraction_is_idempotent_but_distinct_sources_are_kept(self):
        event = ExtractedEvent(
            event_type="launch", title="Product launched", description="A launch",
            event_status="announced", evidence_classification="primary",
            extraction_confidence=0.9,
        )
        item = ExtractedKnowledgeItem(
            item_type="decision", title="Launch decision", description="Launch approved",
            evidence_quote="We approved the launch.", evidence_classification="primary",
            extraction_confidence=0.9,
        )
        result = EventExtractionResult(events=[event], knowledge_items=[item])
        save_events(self.db, self.company.id, "source-one", result)
        save_events(self.db, self.company.id, "source-one", result)
        self.assertEqual(1, self.db.query(ProductEvent).count())
        self.assertEqual(1, self.db.query(KnowledgeItem).count())

        save_events(self.db, self.company.id, "source-two", result)
        self.assertEqual(2, self.db.query(ProductEvent).count())
        self.assertEqual(2, self.db.query(KnowledgeItem).count())

    def test_source_updates_do_not_remove_other_company_records(self):
        original = save_source(
            self.db, self.company.id, "https://example.com/keep", "Existing evidence",
        )
        save_source(
            self.db, self.company.id, "https://example.com/new", "New evidence",
        )
        self.assertIsNotNone(self.db.get(SourceDocument, original.id))
        self.assertEqual(2, self.db.query(SourceDocument).count())

    def test_event_relationship_requires_company_evidence_and_deduplicates(self):
        source = save_source(
            self.db, self.company.id, "https://example.com/evidence", "Supported events"
        )
        events = EventExtractionResult(
            events=[
                ExtractedEvent(
                    event_type="proposal",
                    title="Charging support proposed",
                    evidence_quote="Charging support is proposed.",
                    evidence_classification="primary",
                    extraction_confidence=0.9,
                ),
                ExtractedEvent(
                    event_type="decision",
                    title="Charging support approved",
                    evidence_quote="Charging support is approved.",
                    evidence_classification="primary",
                    extraction_confidence=0.9,
                ),
            ]
        )
        save_events(self.db, self.company.id, source.id, events)
        event_ids = [
            event.id
            for event in self.db.query(ProductEvent).filter_by(
                company_id=self.company.id
            ).all()
        ]
        payload = EventRelationshipCreate(
            from_event_id=event_ids[0],
            to_event_id=event_ids[1],
            relation_type="RESULTED_IN",
            source_ids=[source.id],
            evidence_classification="supported_relationship",
            explanation="Both events appear in the same source.",
        )
        first = company_routes.create_event_relationship(
            self.company.id, payload, self.db
        )
        second = company_routes.create_event_relationship(
            self.company.id, payload, self.db
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual([source.id], second["relationship"].source_ids)

    def test_internal_source_upsert_preserves_synthetic_flag_and_hashes_changes(self):
        first, created = save_internal_source(
            self.db,
            self.company.id,
            source_type="slack",
            source_identifier="slack:message-1",
            title="[SYNTHETIC DEMO] Proposal",
            content_text="We propose adding charging support.",
            is_synthetic=True,
        )
        second, created_again = save_internal_source(
            self.db,
            self.company.id,
            source_type="slack",
            source_identifier="slack:message-1",
            title="[SYNTHETIC DEMO] Proposal",
            content_text="We approved adding charging support.",
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual("We approved adding charging support.", second.content_text)
        self.assertTrue(second.is_synthetic)
        linked_first, _ = save_internal_source(
            self.db,
            self.company.id,
            source_type="notion",
            source_url="https://www.example.com/design/?utm_source=import",
            content_text="Imported project notes.",
        )
        linked_second, created_again = save_internal_source(
            self.db,
            self.company.id,
            source_type="notion",
            source_url="https://example.com/design",
            content_text="Imported project notes.",
        )
        self.assertFalse(created_again)
        self.assertEqual(linked_first.id, linked_second.id)
        self.assertEqual(2, self.db.query(type(second)).count())

    def test_html_processor_keeps_titles_and_paragraphs_without_navigation(self):
        result = process_html(
            "<html><head><title>Product update</title></head><body>"
            "<nav>Menu item</nav><main><h1>Launch</h1><p>Product is available.</p>"
            "<script>ignore()</script></main></body></html>"
        )
        self.assertEqual("Product update", result.title)
        self.assertIn("Launch", result.text)
        self.assertIn("Product is available.", result.text)
        self.assertNotIn("Menu item", result.text)
        self.assertNotIn("ignore()", result.text)

    def test_source_classification_and_candidate_validation(self):
        official = classify_source("https://www.example.com/news", "example.com")
        regulator = classify_source("https://www.sec.gov/filing", "example.com")
        news = classify_source("https://www.reuters.com/article", "example.com")
        self.assertEqual("target_company", official["source_owner_type"])
        self.assertEqual(1, official["source_authority_level"])
        self.assertEqual(2, regulator["source_authority_level"])
        self.assertEqual("news_organization", news["source_owner_type"])
        self.assertIsNone(make_candidate("javascript:alert(1)", "example.com", "test"))

    def test_evidence_quotes_must_appear_in_source(self):
        text = "The team approved the limited test.\nFurther checks are required."
        self.assertTrue(_has_source_quote("The team approved the limited test.", text))
        self.assertTrue(_has_source_quote("approved   the limited test.", text))
        self.assertFalse(_has_source_quote("The team launched the product.", text))

    def test_event_and_knowledge_dates_share_one_iso_parser(self):
        self.assertEqual("2026-11-12", parse_date("2026-11-12T09:30:00Z").date().isoformat())
        self.assertIsNone(parse_date("not-a-date"))

    def test_fetcher_reports_http_failures_and_respects_redirect_policy(self):
        response = SimpleNamespace(
            status_code=403,
            is_redirect=False,
            is_permanent_redirect=False,
            headers={},
            url="https://example.org/private",
            raise_for_status=lambda: (_ for _ in ()).throw(
                requests.HTTPError(
                    "403 Client Error",
                    response=SimpleNamespace(status_code=403),
                )
            ),
        )
        with patch("app.research.fetcher.is_url_allowed", return_value=(True, None)), \
             patch("app.research.fetcher.requests.get", return_value=response):
            result = fetch_url("https://example.org/private")
        self.assertFalse(result.ok)
        self.assertEqual(403, result.status_code)

        redirect = SimpleNamespace(
            status_code=302,
            is_redirect=True,
            is_permanent_redirect=False,
            headers={"Location": "https://blocked.example/path"},
        )
        with patch(
            "app.research.fetcher.is_url_allowed",
            side_effect=[(True, None), (False, "disallowed by robots.txt")],
        ), patch("app.research.fetcher.requests.get", return_value=redirect) as get:
            result = fetch_url("https://example.org/redirect")
        self.assertIn("robots.txt", result.error)
        get.assert_called_once()

    def test_company_and_internal_ingestion_api_and_idempotent_extraction(self):
        company = company_routes.create_company(
            CompanyCreate(name="API Company", website="https://example.com"),
            self.db,
        )
        updated_company = company_routes.update_company(
            company.id,
            company_routes.CompanyUpdate(description="API test company"),
            self.db,
        )
        self.assertEqual("API test company", updated_company.description)
        ingested = company_routes.ingest_internal_source(
            company.id,
            InternalSourceCreate(
                source_type="meeting_transcript",
                source_identifier="meeting:1",
                title="[SYNTHETIC DEMO] Review Meeting",
                content_text="The team approved the charging support prototype.",
                is_synthetic=True,
            ),
            self.db,
        )
        source_id = ingested["source"].id
        extracted = EventExtractionResult(
            knowledge_items=[
                ExtractedKnowledgeItem(
                    item_type="decision",
                    title="Prototype approved",
                    description="The team approved the charging support prototype.",
                    status="approved",
                    evidence_quote="The team approved the charging support prototype.",
                    evidence_classification="primary",
                    extraction_confidence=0.95,
                )
            ]
        )
        with patch.object(company_routes, "extract_events", return_value=extracted) as model:
            first_run = company_routes.extract_company_events(company.id, self.db)
            self.assertEqual(1, first_run["knowledge_items_created"])
            second_run = company_routes.extract_company_events(company.id, self.db)
            self.assertEqual(1, second_run["sources_skipped"])
            self.assertEqual(1, model.call_count)

        items = company_routes.list_knowledge_items(company.id, self.db)
        self.assertEqual(1, len(items["knowledge_items"]))
        source = company_routes.get_source(company.id, source_id, self.db)
        self.assertTrue(source.is_synthetic)

    def test_research_endpoint_saves_full_pages_and_marks_snippets_partial(self):
        candidate = {
            "url": "https://news.example.com/tesla-update",
            "source_owner_type": "news_organization",
            "is_target_company_official": False,
            "is_other_company_official": False,
            "source_authority_level": 3,
            "discovery_method": "ddgs_search",
            "search_query": "Example latest news",
            "search_title": "Example company update",
            "search_snippet": "A sufficiently long search-result summary with useful context "
            "that is clearly a snippet rather than an entire article.",
        }
        with patch.object(company_routes, "discover_sources", return_value=[candidate]), \
             patch.object(
                 company_routes,
                 "fetch_url",
                 side_effect=lambda url: FetchResult(
                     url, url, status_code=403, error="403 Forbidden"
                 ),
             ) as fetch:
            first = company_routes.research_company(self.company.id, self.db)
            self.assertEqual("partial", first["status"])
            self.assertEqual(1, first["sources_failed"])
            self.assertEqual(1, first["sources_saved"])
            saved = self.db.query(SourceDocument).one()
            self.assertEqual("search_snippet", saved.content_kind)
            self.assertEqual("partial", saved.processing_status)
            self.assertIn("403", saved.fetch_error)

            second = company_routes.research_company(self.company.id, self.db)
            self.assertEqual(1, second["sources_skipped"])
            self.assertEqual(1, fetch.call_count)

    def test_research_endpoint_persists_full_page_title_and_discovery_metadata(self):
        candidate = {
            "url": "https://reuters.com/example-story/",
            "source_owner_type": "news_organization",
            "is_target_company_official": False,
            "is_other_company_official": False,
            "source_authority_level": 3,
            "discovery_method": "ddgs_search",
            "search_query": "Example latest news",
            "search_title": "Search title",
            "search_snippet": "Search summary",
        }
        html = (
            "<html><head><title>Article title</title></head><body>"
            "<nav>Navigation</nav><main><h1>Company update</h1>"
            "<p>This article contains enough readable text to be stored as a full webpage.</p>"
            "</main></body></html>"
        )
        with patch.object(company_routes, "discover_sources", return_value=[candidate]), \
             patch.object(
                 company_routes,
                 "fetch_url",
                 return_value=FetchResult(candidate["url"], candidate["url"], content=html, status_code=200),
             ):
            result = company_routes.research_company(self.company.id, self.db)
        source = self.db.query(SourceDocument).one()
        self.assertEqual("completed", result["status"])
        self.assertEqual(1, result["sources_fetched"])
        self.assertEqual("Article title", source.title)
        self.assertEqual("news_article", source.source_type)
        self.assertEqual(3, source.source_authority_level)
        self.assertEqual("ddgs_search", source.discovery_method)
        self.assertEqual("full_page", source.content_kind)
        self.assertIn("Company update", source.content_text)


if __name__ == "__main__":
    unittest.main()
