from app.models import Company
from app.research import competitors


def test_identical_competitor_discovery_is_reused(monkeypatch):
    competitors._DISCOVERY_CACHE.clear()
    company = Company(
        id="synthetic-company-id",
        name="[SYNTHETIC] Northstar",
        website="https://northstar.example",
        industry="consumer technology",
    )
    calls = []
    monkeypatch.setattr(competitors, "_search_web", lambda query: (calls.append(query) or []))
    try:
        first = competitors.discover_and_ingest_competitors(
            db=None,
            proposal_company=company,
            proposal_title="Synthetic checkout pilot",
            proposal_description="Evaluate a controlled checkout pilot for selected users.",
        )
        second = competitors.discover_and_ingest_competitors(
            db=None,
            proposal_company=company,
            proposal_title="Synthetic checkout pilot",
            proposal_description="Evaluate a controlled checkout pilot for selected users.",
        )
        assert len(calls) == 1
        assert first["discovery_cache_hit"] is False
        assert second["discovery_cache_hit"] is True
        assert second["evidence_origin"] == "cached"
        assert second["companies_discovered"] == 0
    finally:
        competitors._DISCOVERY_CACHE.clear()
