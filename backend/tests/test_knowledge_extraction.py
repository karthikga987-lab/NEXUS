import json

from app.intelligence.extraction import (
    DocumentExtraction,
    _parse_structured_json,
    extract_events,
    validate_extracted_knowledge_item,
)


def test_old_event_only_json_defaults_to_no_knowledge_items():
    parsed = _parse_structured_json('{"events": []}')
    assert parsed == {"events": [], "knowledge_items": []}


def test_valid_knowledge_item_retains_exact_source_provenance(monkeypatch):
    source_text = (
        "The team proposed testing a faster checkout flow to reduce abandonment."
    )
    quote = source_text
    raw_item = {
        "item_type": "proposal",
        "title": "Team proposed faster checkout testing",
        "description": "The team proposed a faster checkout flow.",
        "subject_name": "checkout",
        "actor": "team",
        "status": "proposed",
        "item_date": None,
        "item_date_quote": None,
        "evidence_quote": quote,
        "evidence_classification": "documented",
        "extraction_confidence": 0.91,
    }
    monkeypatch.setattr(
        "app.intelligence.extraction._ask_ollama",
        lambda text: {"events": [], "knowledge_items": [raw_item]},
    )

    result = extract_events(
        source_text=source_text,
        source_id="synthetic-source-id",
        company_id="synthetic-company-id",
    )

    assert isinstance(result, DocumentExtraction)
    assert result == []
    assert len(result.knowledge_items) == 1
    item = result.knowledge_items[0]
    assert item["source_id"] == "synthetic-source-id"
    assert item["company_id"] == "synthetic-company-id"
    assert item["evidence_quote"] == quote
    assert item["item_date"] is None
    assert item["status"] == "proposed"


def test_knowledge_item_date_is_kept_only_when_quote_supports_it():
    quote = "The team approved the pilot on March 3, 2024."
    valid = validate_extracted_knowledge_item(
        {
            "item_type": "decision",
            "title": "Team approved pilot",
            "description": "The team approved the pilot.",
            "subject_name": "pilot",
            "actor": "team",
            "status": "approved",
            "item_date": "2024-03-03",
            "item_date_quote": "March 3, 2024",
            "evidence_quote": quote,
            "evidence_classification": "documented",
            "extraction_confidence": 0.8,
        },
        source_text=quote,
        source_id="synthetic-source-id",
        company_id="synthetic-company-id",
    )
    assert valid is not None
    assert valid["item_date"].isoformat() == "2024-03-03T00:00:00+00:00"

    missing_date = validate_extracted_knowledge_item(
        {
            "item_type": "decision",
            "title": "Team approved pilot",
            "description": "The team approved the pilot.",
            "subject_name": "pilot",
            "actor": "team",
            "status": "approved",
            "item_date": "2024-03-04",
            "item_date_quote": "March 3, 2024",
            "evidence_quote": quote,
            "evidence_classification": "documented",
            "extraction_confidence": 0.8,
        },
        source_text=quote,
        source_id="synthetic-source-id",
        company_id="synthetic-company-id",
    )
    assert missing_date is not None
    assert missing_date["item_date"] is None


def test_unsupported_knowledge_summary_is_rejected():
    quote = "The dashboard displays weekly activity."
    item = validate_extracted_knowledge_item(
        {
            "item_type": "decision",
            "title": "Team approved shipping change",
            "description": "The team approved a shipping change.",
            "evidence_quote": quote,
            "status": "approved",
            "evidence_classification": "documented",
        },
        source_text=quote,
        source_id="synthetic-source-id",
        company_id="synthetic-company-id",
    )
    assert item is None


def test_structured_knowledge_item_enums_reject_unsupported_values():
    response = {
        "events": [],
        "knowledge_items": [{
            "item_type": "guess",
            "title": "Unsupported type",
            "description": "Unsupported type value.",
            "subject_name": None,
            "actor": None,
            "status": "unknown",
            "item_date": None,
            "item_date_quote": None,
            "evidence_quote": "The source states this.",
            "evidence_classification": "documented",
            "extraction_confidence": None,
        }],
    }
    try:
        _parse_structured_json(json.dumps(response))
    except Exception as exc:
        assert "item_type" in str(exc)
    else:
        raise AssertionError("Unsupported knowledge item type was accepted")
