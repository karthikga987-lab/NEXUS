
from enum import Enum
from typing import Any


class EvidenceStatus(str, Enum):
    DOCUMENTED = "documented"
    SUPPORTED = "supported"
    CORRELATION = "correlation"
    UNKNOWN = "unknown"


class EvidenceValidator:
    """
    Validates extracted claims against their source evidence.

    Never treats unsupported claims as documented facts.
    """

    @staticmethod
    def validate_claim(
        claim: str,
        source_id: str | None,
        source_text: str | None,
        confidence: float | None = None,
    ) -> dict[str, Any]:

        claim = claim.strip() if claim else ""
        source_text = source_text or ""

        if not claim or not source_id or not source_text.strip():
            return {
                "claim": claim,
                "source_id": source_id,
                "evidence_status": EvidenceStatus.UNKNOWN.value,
                "confidence": None,
                "verified": False,
                "reason": "Missing claim or source evidence.",
            }

        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1.")

        # Conservative lexical check, not semantic verification.
        normalized_claim = " ".join(claim.lower().split())
        normalized_source = " ".join(source_text.lower().split())

        if normalized_claim in normalized_source:
            status = EvidenceStatus.DOCUMENTED
            verified = True
            reason = "Exact claim text found in source."

        else:
            status = EvidenceStatus.UNKNOWN
            verified = False
            reason = (
                "Claim was not found verbatim. "
                "Semantic verification is required."
            )

        return {
            "claim": claim,
            "source_id": source_id,
            "evidence_status": status.value,
            "confidence": confidence,
            "verified": verified,
            "reason": reason,
        }

    @staticmethod
    def validate_event(event: dict) -> dict[str, Any]:
        """
        An extracted event must have at least one source ID.
        """

        source_ids = event.get("source_ids") or []

        valid = bool(
            isinstance(source_ids, list)
            and any(isinstance(s, str) and s.strip() for s in source_ids)
        )

        return {
            "valid": valid,
            "event": event,
            "reason": (
                "Source evidence available."
                if valid
                else "Event rejected: no source evidence."
            ),
        }
