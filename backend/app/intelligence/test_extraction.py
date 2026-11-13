
from app.intelligence.extraction import (
    validate_extracted_event,
    _is_completed_event_quote,
    _is_explicit_reason_quote,
    _is_specific_outcome,
    _normalize_event_type,
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


def test_rejects_event_type_not_supported_by_exact_quote():
    source = (
        "TRESemmé Professional has just launched in the UK & Ireland, "
        "redefining social-first, influencer marketing."
    )
    event = {
        "product_name": "TRESemmé Professional",
        "event_type": "incident",
        "title": "TRESemmé Professional Appoints Influencer Partnerships",
        "evidence_quote": source,
        "extraction_confidence": 0.95,
        "field_quotes": {"product_name": "TRESemmé Professional"},
    }

    assert validate_extracted_event(
        event, source, "synthetic-source", "synthetic-company"
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


def test_validates_experiment_date_reason_and_reported_outcome():
    source = (
        "Acme ran a checkout experiment on May 1, 2024. "
        "The company said it ran the test to improve completion. "
        "Acme reported that completion increased by 8%."
    )
    assert _validate_event_date(
        "2024-05-01", "May 1, 2024", source
    ) == "2024-05-01"
    assert _is_explicit_reason_quote(
        "The company said it ran the test to improve completion.", source
    ) is True
    assert _is_explicit_reason_quote(
        "to improve completion", source
    ) is True
    assert _is_explicit_reason_quote(
        "to increase revenue", source
    ) is False
    assert _is_specific_outcome(
        "Completion increased by 8%",
        "completion increased by 8%",
        source,
    ) is True


def test_omits_unsupported_reason_and_outcome():
    source = "Acme launched Acme Pay on June 10, 2025."
    event = {
        "product_name": "Acme Pay",
        "event_type": "product_launch",
        "title": "Acme Pay launch",
        "event_date": "2025-06-10",
        "stated_reason": "To increase revenue",
        "outcome_summary": "Revenue increased by 20%",
        "evidence_quote": source,
        "field_quotes": {
            "product_name": "Acme Pay",
            "event_date": "June 10, 2025",
            "stated_reason": "To increase revenue",
            "outcome_summary": "Revenue increased by 20%",
        },
    }

    result = validate_extracted_event(
        event, source, "synthetic-source", "synthetic-company"
    )

    assert result is not None
    assert result["event_date"] == "2025-06-10"
    assert result["stated_reason"] is None
    assert result["outcome_summary"] is None


def test_recovers_exact_event_quote_when_model_concatenates_passages():
    source = (
        "Aster announced the launch of Orbit Desk on February 12, 2024. "
        "The office will be closed the following Monday. "
        "The product became available to customers that day."
    )
    event = {
        "product_name": "Orbit Desk",
        "event_type": "product_launch",
        "title": "Orbit Desk launched",
        "event_date": "2024-02-12",
        "stated_reason": None,
        "outcome_summary": "became available to customers that day",
        # This quote is a concatenation with an omitted original sentence;
        # the exact product field quote is itself a supported event sentence.
        "evidence_quote": (
            "Aster announced the launch of Orbit Desk on February 12, 2024. "
            "The product became available to customers that day."
        ),
        "field_quotes": {
            "product_name": "Aster announced the launch of Orbit Desk on February 12, 2024.",
            "event_date": "February 12, 2024",
            "stated_reason": None,
            "outcome_summary": "became available to customers that day",
        },
    }

    result = validate_extracted_event(
        event, source, "synthetic-source", "synthetic-company"
    )

    assert result is not None
    assert result["evidence_quote"] == event["field_quotes"]["product_name"]
    assert result["outcome_summary"] == "became available to customers that day"


def test_completed_action_verbs_cover_removals_reformulations_and_tests():
    examples = [
        "Aster removed the legacy export feature from Orbit Desk.",
        "Aster reformulated its reusable cleaning concentrate.",
        "Aster conducted a checkout experiment for Orbit Desk.",
        "Aster approved a decision to end Aster Home support.",
        "Aster raised the Orbit Desk Pro monthly price.",
    ]
    for sentence in examples:
        assert _is_completed_event_quote(sentence, sentence)


def test_decision_phrase_is_not_misclassified_as_feature_removal():
    assert _normalize_event_type(
        "feature_removal",
        "Aster Home support ending",
        "The board approved a decision to end support for Aster Home.",
    ) == "strategic_decision"


def test_experiment_hypothesis_is_an_explicit_reason():
    quote = "The experiment tested whether a shorter form improved completion."
    assert _is_explicit_reason_quote(quote, quote)
