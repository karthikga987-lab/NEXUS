
from app.intelligence.evidence import EvidenceValidator


def test_documented_claim():
    result = EvidenceValidator.validate_claim(
        claim="We launched Google Maps.",
        source_id="source-123",
        source_text="We launched Google Maps.",
    )

    assert result["evidence_status"] == "documented"
    assert result["verified"] is True


def test_missing_evidence():
    result = EvidenceValidator.validate_claim(
        claim="We launched a new feature.",
        source_id=None,
        source_text=None,
    )

    assert result["evidence_status"] == "unknown"
    assert result["verified"] is False


def test_event_without_source():
    result = EvidenceValidator.validate_event({
        "title": "New feature launched",
        "source_ids": [],
    })

    assert result["valid"] is False


def test_event_with_source():
    result = EvidenceValidator.validate_event({
        "title": "New feature launched",
        "source_ids": ["source-123"],
    })

    assert result["valid"] is True
