import json

import pytest

from app.intelligence import extraction


SOURCE = "Acme launched Acme Pay on March 3, 2024."
EVENT = {
    "product_name": "Acme Pay",
    "event_type": "product_launch",
    "title": "Acme launched Acme Pay on March 3, 2024.",
    "event_date": "2024-03-03",
    "evidence_quote": SOURCE,
    "field_quotes": {
        "product_name": SOURCE,
        "event_date": "March 3, 2024",
    },
}


class _Response:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({
            "done_reason": "stop",
            "message": {"content": self.content},
        }).encode("utf-8")


def _mock_ollama(monkeypatch, responses):
    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        response = responses[min(len(calls) - 1, len(responses) - 1)]
        return _Response(response)

    monkeypatch.setattr(extraction.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(extraction.time, "sleep", lambda seconds: None)
    return calls


def test_valid_model_json_extracts_event_with_source_provenance(monkeypatch):
    calls = _mock_ollama(
        monkeypatch,
        [json.dumps({"events": [EVENT]})],
    )

    events = extraction.extract_events(
        SOURCE,
        source_id="synthetic-source-id",
        company_id="synthetic-company-id",
    )

    assert len(events) == 1
    assert events[0]["source_ids"] == ["synthetic-source-id"]
    assert events[0]["evidence_quote"] == SOURCE
    assert events[0]["event_date"] == "2024-03-03"
    assert events[0]["stated_reason"] is None
    assert events[0]["outcome_summary"] is None
    request_body = json.loads(calls[0][0].data.decode("utf-8"))
    assert request_body["model"] == extraction.OLLAMA_MODEL
    assert request_body["format"] == extraction.EVENT_RESPONSE_SCHEMA
    assert request_body["stream"] is False
    assert request_body["options"]["num_predict"] == 2048
    assert "Return exactly one JSON object" in request_body["messages"][1]["content"]
    assert "include that completed partnership as an event" in request_body["messages"][1]["content"]


def test_markdown_fenced_json_is_accepted(monkeypatch):
    calls = _mock_ollama(
        monkeypatch,
        ["```json\n{" + '"events": []' + "}\n```"],
    )

    assert extraction.extract_events(
        "A current product description with no event.",
        "synthetic-source-id",
        "synthetic-company-id",
    ) == []
    assert len(calls) == 1


def test_empty_event_array_is_a_valid_extraction(monkeypatch):
    _mock_ollama(monkeypatch, ['{"events": []}'])

    assert extraction.extract_events(
        "The product is currently available to customers.",
        "synthetic-source-id",
        "synthetic-company-id",
    ) == []


def test_malformed_json_gets_one_bounded_retry(monkeypatch):
    calls = _mock_ollama(
        monkeypatch,
        ["not json", '{"events": []}'],
    )

    assert extraction.extract_events(
        "A current product description.",
        "synthetic-source-id",
        "synthetic-company-id",
    ) == []
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1] == 180


def test_invalid_json_after_retry_raises_controlled_error(monkeypatch):
    calls = _mock_ollama(monkeypatch, ["not json"])

    with pytest.raises(
        extraction.ExtractionError,
        match="invalid extraction response",
    ):
        extraction.extract_events(
            "A current product description.",
            "synthetic-source-id",
            "synthetic-company-id",
        )

    assert len(calls) == 3
    budgets = [
        json.loads(request.data.decode("utf-8"))["options"]["num_predict"]
        for request, _timeout in calls
    ]
    assert budgets == [2048, 4096, 8192]


def test_truncated_response_gets_bounded_larger_budget_retry(monkeypatch):
    complete = json.dumps({"events": [], "knowledge_items": []})
    calls = _mock_ollama(
        monkeypatch,
        ['{"events": [{"title": "truncated', '```json\n{"events": []', complete],
    )

    assert extraction.extract_events(
        "A current product description.",
        "synthetic-source-id",
        "synthetic-company-id",
    ) == []
    budgets = [
        json.loads(request.data.decode("utf-8"))["options"]["num_predict"]
        for request, _timeout in calls
    ]
    assert budgets == [2048, 4096, 8192]


def test_long_source_starts_with_larger_bounded_budget(monkeypatch):
    complete = json.dumps({"events": [], "knowledge_items": []})
    calls = _mock_ollama(monkeypatch, ["not json", complete])
    source_text = "[SYNTHETIC LONG SOURCE] " + ("Acme product information. " * 400)

    assert extraction._ask_ollama(source_text) == {
        "events": [],
        "knowledge_items": [],
    }
    budgets = [
        json.loads(request.data.decode("utf-8"))["options"]["num_predict"]
        for request, _timeout in calls
    ]
    assert budgets == [8192, 12288]
    assert extraction.EVENT_RESPONSE_SCHEMA["properties"]["knowledge_items"]["maxItems"] == 4


def test_invalid_structured_event_is_retried_and_then_rejected(monkeypatch):
    invalid = {
        "events": [{**EVENT, "event_type": "invented_type"}],
    }
    calls = _mock_ollama(
        monkeypatch,
        [json.dumps(invalid), '{"events": []}'],
    )

    assert extraction.extract_events(
        SOURCE,
        "synthetic-source-id",
        "synthetic-company-id",
    ) == []
    assert len(calls) == 2


def test_product_description_does_not_become_a_launch():
    product_description = (
        "Samsung AI washer-dryer includes AI washing features and a large display."
    )
    unsupported_launch = {
        "product_name": "Samsung AI washer-dryer",
        "event_type": "product_launch",
        "title": "Samsung AI washer-dryer launch",
        "evidence_quote": product_description,
        "field_quotes": {"product_name": product_description},
    }

    assert extraction.validate_extracted_event(
        unsupported_launch,
        product_description,
        "synthetic-source-id",
        "synthetic-company-id",
    ) is None


def test_explicit_product_partnership_is_retained_as_an_evidenced_event():
    source = (
        "Ceva and boAt today announced they have formed a strategic "
        "partnership to develop technology for boAt earbuds."
    )
    event = {
        "product_name": "boAt earbuds",
        "event_type": "partnership",
        "title": "Ceva and boAt form a product technology partnership",
        "description": "The companies formed a partnership concerning boAt earbuds.",
        "event_date": None,
        "stated_reason": None,
        "outcome_summary": None,
        "extraction_confidence": 0.9,
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "boAt earbuds",
            "event_date": None,
            "stated_reason": None,
            "outcome_summary": None,
        },
    }

    validated = extraction.validate_extracted_event(
        event,
        source,
        "synthetic-source-id",
        "synthetic-company-id",
    )

    assert validated is not None
    assert validated["event_type"] == "partnership"
    assert validated["evidence_quote"] == source
    assert validated["event_date"] is None


def test_whitespace_normalized_model_quote_is_restored_to_verbatim_source():
    source = (
        "Acme launched Acme Pay on March 3, 2024.\n\n"
        "Customers can now use Acme Pay for checkout."
    )
    event = {
        **EVENT,
        "title": "Acme Pay launched",
        "evidence_quote": (
            "Acme launched Acme Pay on March 3, 2024. "
            "Customers can now use Acme Pay for checkout."
        ),
        "field_quotes": {
            "product_name": "Acme Pay",
            "event_date": "March 3, 2024",
        },
    }

    validated = extraction.validate_extracted_event(
        event,
        source,
        "synthetic-source-id",
        "synthetic-company-id",
    )

    assert validated is not None
    assert validated["evidence_quote"] == source
    assert validated["evidence_quote"] in source
    assert validated["event_date"] == "2024-03-03"


def test_duplicate_model_events_with_same_source_evidence_are_deduplicated(
    monkeypatch,
):
    duplicate = {**EVENT, "title": "Acme Pay debut"}
    _mock_ollama(
        monkeypatch,
        [json.dumps({"events": [EVENT, duplicate]})],
    )

    events = extraction.extract_events(
        SOURCE,
        "synthetic-source-id",
        "synthetic-company-id",
    )

    assert len(events) == 1
    assert events[0]["title"] == EVENT["title"]


def test_duplicate_event_quote_is_not_persisted_as_knowledge_item(monkeypatch):
    source = (
        "Ceva and boAt today announced they have formed a strategic "
        "partnership to develop technology for boAt earbuds."
    )
    event = {
        "product_name": "boAt earbuds",
        "event_type": "partnership",
        "title": "Ceva and boAt form a product technology partnership",
        "description": None,
        "event_date": None,
        "stated_reason": None,
        "outcome_summary": None,
        "extraction_confidence": 0.9,
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "boAt earbuds",
            "event_date": None,
            "stated_reason": None,
            "outcome_summary": None,
        },
    }
    knowledge_item = {
        "item_type": "decision",
        "title": "Strategic Partnership Between Ceva and boAt",
        "description": "Ceva and boAt formed a strategic partnership.",
        "subject_name": None,
        "actor": "Ceva and boAt",
        "status": "unknown",
        "item_date": None,
        "item_date_quote": None,
        "evidence_quote": source,
        "evidence_classification": "documented",
        "extraction_confidence": 0.9,
    }
    _mock_ollama(
        monkeypatch,
        [json.dumps({"events": [event], "knowledge_items": [knowledge_item]})],
    )

    result = extraction.extract_events(
        source,
        "synthetic-source-id",
        "synthetic-company-id",
    )

    assert len(result) == 1
    assert result[0]["event_type"] == "partnership"
    assert result.knowledge_items == []


def test_explicit_simplification_rationale_is_retained():
    source = (
        "Acme launched Acme Pay. We built it to simplify checkout "
        "for small businesses."
    )
    event = {
        "product_name": "Acme Pay",
        "event_type": "product_launch",
        "title": "Acme launched Acme Pay.",
        "event_date": None,
        "stated_reason": "Simplify checkout for small businesses",
        "outcome_summary": None,
        "evidence_quote": "Acme launched Acme Pay.",
        "field_quotes": {
            "product_name": "Acme Pay",
            "event_date": None,
            "stated_reason": "We built it to simplify checkout for small businesses.",
            "outcome_summary": None,
        },
    }

    validated = extraction.validate_extracted_event(
        event,
        source,
        "synthetic-source-id",
        "synthetic-company-id",
    )

    assert validated is not None
    assert validated["stated_reason"] == "Simplify checkout for small businesses"
