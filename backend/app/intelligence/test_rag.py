from app.intelligence.rag import _build_verified_claims


def sample_claim():
    return {
        "statement": "Google Maps launched offline maps.",
        "claim_type": "factual_observation",
        "candidate_source_ids": ["source-123"],
        "relevance_category": "direct_match",
    }


def sample_evidence():
    return {
        "source-123": {
            "source_id": "source-123",
            "source_title": "Google Maps announcement",
            "source_url": "https://example.com/source",
            "source_company_name": "Google",
            "evidence_scope": "internal",
        }
    }


def test_rag_accepts_claim_with_verified_supporting_quote():
    verification = {
        (0, "source-123"): {
            "supporting_quote": "Google Maps launched offline maps.",
            "verification_method": "exact_quote",
            "passage_index": 0,
        }
    }

    verified, unsupported = _build_verified_claims(
        [sample_claim()], verification, sample_evidence(), False
    )

    assert len(verified) == 1
    assert unsupported == []
    assert verified[0]["verification_status"] == "textually_supported"
    assert verified[0]["citations"][0]["source_id"] == "source-123"


def test_rag_rejects_claim_without_verification_result():
    verified, unsupported = _build_verified_claims(
        [sample_claim()], {}, sample_evidence(), False
    )

    assert verified == []
    assert len(unsupported) == 1
    assert unsupported[0]["verification_status"] == "unsupported"
    assert unsupported[0]["citations"] == []


def test_rag_rejects_citation_for_unknown_source():
    verification = {
        (0, "source-123"): {
            "supporting_quote": "Google Maps launched offline maps.",
            "verification_method": "exact_quote",
            "passage_index": 0,
        }
    }

    verified, unsupported = _build_verified_claims(
        [sample_claim()], verification, {}, False
    )

    assert verified == []
    assert len(unsupported) == 1
    assert unsupported[0]["verification_status"] == "unsupported"


def test_rag_rejects_empty_supporting_quote():
    verification = {
        (0, "source-123"): {
            "supporting_quote": "   ",
            "verification_method": "exact_quote",
            "passage_index": 0,
        }
    }

    verified, unsupported = _build_verified_claims(
        [sample_claim()], verification, sample_evidence(), False
    )

    assert verified == []
    assert len(unsupported) == 1


def test_rag_marks_claim_when_verification_is_unavailable():
    verified, unsupported = _build_verified_claims(
        [sample_claim()], {}, sample_evidence(), True
    )

    assert verified == []
    assert len(unsupported) == 1
    assert unsupported[0]["verification_status"] == "verification_unavailable"


def test_rag_does_not_accept_unverified_second_source():
    evidence = sample_evidence()
    evidence["source-456"] = {
        "source_id": "source-456",
        "source_title": "Unrelated source",
        "source_url": "https://example.com/other",
        "source_company_name": "Google",
        "evidence_scope": "internal",
    }

    claim = sample_claim()
    claim["candidate_source_ids"] = ["source-123", "source-456"]

    verification = {}

    verified, unsupported = _build_verified_claims(
        [claim], verification, evidence, False
    )

    assert verified == []
    assert len(unsupported) == 1
