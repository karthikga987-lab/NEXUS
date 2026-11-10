
from app.intelligence.extraction import (
    validate_extracted_event,
    _is_completed_event_quote,
    _validate_event_date,
)


def test_valid_event():
    source = "Google Maps launched a new offline maps feature on June 10, 2025."

    event = {
        "product_name": "Google Maps",
        "event_type": "feature_launch",
        "title": "Launched offline maps",
        "event_date": "2025-06-10",
        "extraction_confidence": 0.9,
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "Google Maps",
            "event_date": "June 10, 2025",
        },
    }

    result = validate_extracted_event(
        event, source, "source-123", "company-123"
    )

    assert result is not None
    assert result["event_type"] == "feature_launch"
    assert result["event_date"] == "2025-06-10"
    assert result["source_ids"] == ["source-123"]


def test_rejects_fake_quote():
    source = "Google Maps launched offline maps."

    event = {
        "product_name": "Google Maps",
        "event_type": "feature_launch",
        "title": "Launched offline maps",
        "evidence_quote": "Google Maps acquired another company.",
        "field_quotes": {"product_name": "Google Maps"},
    }

    assert validate_extracted_event(
        event, source, "source-123", "company-123"
    ) is None


def test_rejects_invalid_event_type():
    source = "Google Maps launched offline maps."

    event = {
        "product_name": "Google Maps",
        "event_type": "random_event",
        "title": "Launched offline maps",
        "evidence_quote": source,
        "field_quotes": {"product_name": "Google Maps"},
    }

    assert validate_extracted_event(
        event, source, "source-123", "company-123"
    ) is None


def test_accepts_completed_event_quote():
    source = "The feature became available to users on June 10, 2025."
    assert _is_completed_event_quote(source, source) is True


def test_rejects_future_event_quote():
    source = "The company announced that the feature would launch soon."
    assert _is_completed_event_quote(source, source) is False


def test_rejects_unrelated_event_quote():
    source = "The feature became available to users."
    quote = "The company developed the feature to help travelers."

    assert _is_completed_event_quote(quote, source) is False


def test_rejects_product_name_without_supporting_quote():
    source = "The feature became available to users."

    event = {
        "product_name": "Google Maps",
        "event_type": "feature_launch",
        "title": "Offline maps launch",
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "The feature became available to users.",
        },
    }

    assert validate_extracted_event(
        event, source, "source-123", "company-123"
    ) is None


def test_discards_inconsistent_event_date():
    source = "Google Maps launched offline maps on June 10, 2025."

    event = {
        "product_name": "Google Maps",
        "event_type": "feature_launch",
        "title": "Offline maps launch",
        "event_date": "2025-06-11",
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "Google Maps",
            "event_date": "June 10, 2025",
        },
    }

    result = validate_extracted_event(
        event, source, "source-123", "company-123"
    )

    assert result is not None
    assert result["event_date"] is None


def test_date_validator_accepts_matching_date():
    source = "The feature launched on June 10, 2025."

    assert _validate_event_date(
        "2025-06-10", "June 10, 2025", source
    ) == "2025-06-10"


def test_date_validator_rejects_mismatched_date():
    source = "The feature launched on June 10, 2025."

    assert _validate_event_date(
        "2025-06-11", "June 10, 2025", source
    ) is None


def test_date_validator_rejects_quote_not_in_source():
    source = "The feature launched on June 10, 2025."

    assert _validate_event_date(
        "2025-06-10", "June 11, 2025", source
    ) is None


def test_date_validator_rejects_ambiguous_date():
    source = "The feature launched sometime in June 2025."

    assert _validate_event_date(
        "2025-06-10", "June 2025", source
    ) is None


def test_rejects_introductory_phrase_as_reason():
    source = (
        "With our updated plan, Spotify Premium Family subscribers "
        "have access to additional features."
    )

    event = {
        "product_name": "Spotify Premium Family",
        "event_type": "feature_change",
        "title": "Spotify Premium Family update",
        "evidence_quote": (
            "The update is now available in Ireland"
        ),
        "stated_reason": "With our updated plan",
        "outcome_summary": None,
        "field_quotes": {
            "product_name": "Spotify Premium Family",
            "stated_reason": "With our updated plan",
        },
    }

    result = validate_extracted_event(
        event, source, "source-123", "company-123"
    )

    # This source does not contain a completed-event quotation,
    # so this particular event must be rejected.
    assert result is None


def test_rejects_future_rollout_in_outcome():
    
    source = (
            "Spotify Premium Family was updated. The update is now available "
             "in Ireland and will rollout in all markets with Premium Family "
            "this fall."
        
    )

    event = {
        "product_name": "Spotify Premium Family",
        "event_type": "feature_change",
        "title": "Spotify Premium Family update",
        "evidence_quote": source,
        "stated_reason": None,
        "outcome_summary": (
            "The update is now available in Ireland and will rollout "
            "in all markets with Premium Family this fall"
        ),
        "extraction_confidence": 0.9,
        "field_quotes": {
            "product_name": "Spotify Premium Family",
            "outcome_summary": (
                "The update is now available in Ireland and will rollout "
                "in all markets with Premium Family this fall"
            ),
        },
    }

    result = validate_extracted_event(
        event, source, "source-123", "company-123"
    )

    assert result is not None
    assert result["evidence_quote"] == (
        "The update is now available in Ireland"
    )
    assert result["outcome_summary"] is None
