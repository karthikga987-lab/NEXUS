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

    assert len(calls) == 2
    budgets = [
        json.loads(request.data.decode("utf-8"))["options"]["num_predict"]
        for request, _timeout in calls
    ]
    assert budgets == [2048, 4096]


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
