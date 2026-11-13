
import logging
import re
from typing import Any, Callable


logger = logging.getLogger(__name__)


# Words that occur frequently but carry little information about a
# proposal's actual product, problem, audience or solution.
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being",
    "by", "for", "from", "had", "has", "have", "in", "into", "is",
    "it", "its", "of", "on", "or", "our", "that", "the", "their",
    "this", "to", "was", "were", "will", "with", "within", "would",
    "can", "could", "should", "may", "might", "we", "they", "them",
    "these", "those", "which", "who", "what", "when", "where",
    "why", "how", "company", "companies", "business", "businesses",
    "brand", "brands", "product", "products", "service", "services",
    "new", "proposed", "proposal", "initiative", "solution",
    "approach", "strategy", "launch", "development", "develop",
    "improve", "improvement", "customer", "customers",
    "market", "markets", "industry", "industries",
}

_MIN_TERM_LENGTH = 3

_ALLOWED_QWEN_CATEGORIES = {
    "directly_relevant",
    "same_company_historical",
    "competitor_context",
    "general_industry_context",
    "related_insufficient",
    "irrelevant",
    # Retain compatibility with earlier classifier prompts and test doubles.
    "direct_match",
    "contextual",
    "unrelated",
    "insufficient_information",
}

QwenClassifier = Callable[
    [str, str, list[dict[str, Any]]],
    dict[str, Any],
]


def _meaningful_terms(text: str) -> set[str]:
    """Extract meaningful normalized terms from text."""
    if not isinstance(text, str) or not text.strip():
        return set()

    terms = re.findall(r"[a-z0-9]+", text.casefold())

    return {
        term
        for term in terms
        if len(term) >= _MIN_TERM_LENGTH
        and term not in _STOP_WORDS
        and not term.isdigit()
    }


def classify_external_passage_relevance(
    title: str,
    description: str,
    passage: str,
) -> dict[str, Any]:
    """
    Apply the legacy lexical relevance check.

    This is retained as a lightweight fallback for isolated tests and
    callers that do not supply a Qwen classifier. Production proposal
    analysis will use the Qwen classifier.
    """
    proposal_text = f"{title or ''} {description or ''}"

    proposal_terms = _meaningful_terms(proposal_text)
    passage_terms = _meaningful_terms(passage)

    if not proposal_terms or not passage_terms:
        return {
            "category": "unrelated",
            "overlap_count": 0,
            "overlap_terms": [],
            "coverage": 0.0,
        }

    overlap = proposal_terms.intersection(passage_terms)
    overlap_count = len(overlap)
    coverage = overlap_count / len(proposal_terms)

    if overlap_count >= 2 and coverage >= 0.08:
        category = "direct_match"
    elif overlap_count >= 1 and coverage >= 0.04:
        category = "contextual"
    else:
        category = "unrelated"

    return {
        "category": category,
        "overlap_count": overlap_count,
        "overlap_terms": sorted(overlap),
        "coverage": round(coverage, 4),
    }


def _make_enriched_passage(
    item: dict[str, Any],
    category: str,
    reason: str,
    method: str,
    proposal_aspect: str | None = None,
) -> dict[str, Any]:
    """Return a copy with explicit proposal relevance metadata."""
    enriched = {
        **item,
        "proposal_relevance": category,
        "proposal_relevance_reason": reason,
        "proposal_relevance_method": method,
    }
    if proposal_aspect:
        enriched["proposal_aspect"] = proposal_aspect
    return enriched


def _classify_batch_with_qwen(
    title: str,
    description: str,
    passages: list[dict[str, Any]],
    classifier: QwenClassifier,
) -> list[dict[str, Any]]:
    """
    Call the supplied Qwen classifier and validate its complete response.

    A malformed, incomplete or ambiguous response raises ValueError.
    The caller handles that failure by excluding the entire batch.
    """
    response = classifier(title, description, passages)

    if not isinstance(response, dict):
        raise ValueError("Qwen relevance response must be an object.")

    classifications = response.get("classifications")

    if not isinstance(classifications, list):
        raise ValueError("Qwen response has no classifications list.")

    if len(classifications) != len(passages):
        raise ValueError("Qwen returned an incomplete classification batch.")

    validated_by_index: dict[int, dict[str, Any]] = {}

    for entry in classifications:
        if not isinstance(entry, dict):
            raise ValueError("Qwen returned an invalid classification entry.")

        index = entry.get("index")
        category = entry.get("category")
        reason = entry.get("reason")
        proposal_aspect = entry.get("proposal_aspect")

        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("Qwen returned an invalid passage index.")

        if index < 0 or index >= len(passages):
            raise ValueError("Qwen returned an out-of-range passage index.")

        if index in validated_by_index:
            raise ValueError("Qwen returned a duplicate passage index.")

        if category not in _ALLOWED_QWEN_CATEGORIES:
            raise ValueError("Qwen returned an unsupported relevance category.")

        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Qwen returned an empty relevance explanation.")
        if proposal_aspect is None and category in {
            "directly_relevant",
            "same_company_historical",
            "competitor_context",
            "general_industry_context",
            "related_insufficient",
            "irrelevant",
        }:
            raise ValueError("Qwen omitted the proposal aspect.")
        if proposal_aspect is None:
            proposal_aspect = "unspecified"
        if not isinstance(proposal_aspect, str) or not proposal_aspect.strip():
            raise ValueError("Qwen returned an invalid proposal aspect.")

        validated_by_index[index] = {
            "category": category,
            "reason": reason.strip()[:500],
            "proposal_aspect": proposal_aspect.strip()[:160],
        }

    if set(validated_by_index) != set(range(len(passages))):
        raise ValueError("Qwen did not classify every passage.")

    return [
        validated_by_index[index]
        for index in range(len(passages))
    ]


def filter_external_passages(
    title: str,
    description: str,
    passages: list[dict[str, Any]],
    classifier: QwenClassifier | None = None,
    batch_size: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Filter external passages against the proposal.

    When a Qwen classifier is supplied:
    - directly_relevant, competitor_context and industry context are retained
      with their classifications and source provenance.
    - related_insufficient, irrelevant, and same_company_historical labels
      from this external-only pool are excluded.
    - classification failure: the affected batch is excluded.

    When no classifier is supplied, the legacy lexical filter is used.

    Return:
        (accepted_passages, excluded_passages)

    Original retrieval records are never mutated.
    """
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    valid_passages = [
        item for item in passages
        if isinstance(item, dict)
    ]

    if classifier is None:
        for item in valid_passages:
            result = classify_external_passage_relevance(
                title=title,
                description=description,
                passage=item.get("chunk_text", ""),
            )

            enriched = _make_enriched_passage(
                item=item,
                category=result["category"],
                reason=(
                    "Legacy lexical overlap check; "
                    "not a semantic relevance judgment."
                ),
                method="lexical",
            )

            enriched.update({
                "proposal_relevance_overlap": result["overlap_count"],
                "proposal_relevance_terms": result["overlap_terms"],
                "proposal_relevance_coverage": result["coverage"],
            })

            if result["category"] == "unrelated":
                excluded.append(enriched)
            else:
                accepted.append(enriched)

        return accepted, excluded

    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer.")

    for start in range(0, len(valid_passages), batch_size):
        batch = valid_passages[start:start + batch_size]

        try:
            results = _classify_batch_with_qwen(
                title=title,
                description=description,
                passages=batch,
                classifier=classifier,
            )
        except Exception as exc:
            # Fail closed: no passage from a failed batch is accepted.
            logger.warning(
                "Qwen relevance batch failed: batch_start=%d, "
                "batch_size=%d, error=%s",
                start,
                len(batch),
                str(exc)[:300],
            )

            for item in batch:
                excluded.append(
                    _make_enriched_passage(
                        item=item,
                        category="classification_failed",
                        reason=(
                            "Qwen relevance classification failed. "
                            f"Supporting evidence was withheld: {str(exc)[:300]}"
                        ),
                        method="qwen",
                    )
                )
            continue

        for item, result in zip(batch, results):
            enriched = _make_enriched_passage(
                item=item,
                category=result["category"],
                reason=result["reason"],
                method="qwen",
                proposal_aspect=result["proposal_aspect"],
            )

            if result["category"] in {
                "directly_relevant",
                "competitor_context",
                "general_industry_context",
                "direct_match",
            }:
                accepted.append(enriched)
            else:
                excluded.append(enriched)

    category_counts = {
        category: 0
        for category in (
            "direct_match",
            "contextual",
            "unrelated",
            "insufficient_information",
            "classification_failed",
        )
    }

    for item in accepted + excluded:
        category = item.get("proposal_relevance")
        if category in category_counts:
            category_counts[category] += 1

    logger.info(
        "External proposal relevance classification: "
        "received=%d, accepted=%d, excluded=%d, "
        "direct_match=%d, contextual=%d, unrelated=%d, "
        "insufficient_information=%d, classification_failed=%d.",
        len(valid_passages),
        len(accepted),
        len(excluded),
        category_counts["direct_match"],
        category_counts["contextual"],
        category_counts["unrelated"],
        category_counts["insufficient_information"],
        category_counts["classification_failed"],
    )

    return accepted, excluded
