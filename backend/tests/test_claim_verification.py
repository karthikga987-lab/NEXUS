
import pytest

from app.intelligence import claim_verification


def make_claim(statement):
    return {
        "statement": statement,
        "type": "factual_observation",
        "candidate_source_ids": ["source-1"],
    }


def test_exact_supported_claim_is_accepted():
    statement = "The plan supports up to 5 members."

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={
            "source-1": "The plan supports up to 5 members."
        },
    )

    assert error is None
    assert (0, "source-1") in validated
    assert validated[(0, "source-1")]["supporting_quote"] == statement
    assert (
        validated[(0, "source-1")]["verification_method"]
        == "exact_passage_match"
    )


def test_incorrect_number_is_rejected(monkeypatch):
    statement = "The plan supports up to 6 members."
    source_passage = "The plan supports up to 5 members."

    def fake_ollama_batch(items):
        return [
            {
                "request_id": items[0]["request_id"],
                "claim_index": items[0]["claim_index"],
                "source_id": items[0]["source_id"],
                "supported": True,
                "supporting_quote": source_passage,
            }
        ], None

    monkeypatch.setattr(
        claim_verification,
        "_call_ollama_batch",
        fake_ollama_batch,
    )

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={"source-1": source_passage},
    )

    assert (0, "source-1") not in validated
    assert error is not None


def test_missing_up_to_qualifier_is_rejected(monkeypatch):
    statement = "The plan supports 5 members."
    source_passage = "The plan supports up to 5 members."

    def fake_ollama_batch(items):
        return [
            {
                "request_id": items[0]["request_id"],
                "claim_index": items[0]["claim_index"],
                "source_id": items[0]["source_id"],
                "supported": True,
                "supporting_quote": "up to 5 members",
            }
        ], None

    monkeypatch.setattr(
        claim_verification,
        "_call_ollama_batch",
        fake_ollama_batch,
    )

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={"source-1": source_passage},
    )

    assert (0, "source-1") not in validated
    assert error is not None


def test_ollama_timeout_is_reported(monkeypatch):
    statement = "The company introduced a new subscription plan."
    source_passage = "The company announced a subscription update."

    def fake_ollama_batch(items):
        return [], "Evidence verification timed out."

    monkeypatch.setattr(
        claim_verification,
        "_call_ollama_batch",
        fake_ollama_batch,
    )

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={"source-1": source_passage},
    )

    assert validated == {}
    assert error is not None
    assert "timed out" in error.lower()


def test_missing_verification_result_is_reported(monkeypatch):
    statement = "The company introduced a new subscription plan."
    source_passage = "The company announced a subscription update."

    def fake_ollama_batch(items):
        return [], None

    monkeypatch.setattr(
        claim_verification,
        "_call_ollama_batch",
        fake_ollama_batch,
    )

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={"source-1": source_passage},
    )

    assert validated == {}
    assert error is not None
    assert "did not produce accepted evidence" in error.lower()


def test_fabricated_supporting_quote_is_rejected(monkeypatch):
    statement = "The plan supports up to 5 members."
    source_passage = "The plan supports up to 5 profiles."

    def fake_ollama_batch(items):
        return [
            {
                "request_id": items[0]["request_id"],
                "claim_index": items[0]["claim_index"],
                "source_id": items[0]["source_id"],
                "supported": True,
                "supporting_quote": "The plan supports up to 5 members.",
            }
        ], None

    monkeypatch.setattr(
        claim_verification,
        "_call_ollama_batch",
        fake_ollama_batch,
    )

    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim(statement)],
        source_text_by_id={"source-1": source_passage},
    )

    assert (0, "source-1") not in validated
    assert error is not None


def test_claim_with_no_source_passage_is_not_verified():
    validated, error = claim_verification.verify_claim_citations(
        claims=[make_claim("The company launched a new plan.")],
        source_text_by_id={"source-1": ""},
    )

    assert validated == {}
    assert error is None
