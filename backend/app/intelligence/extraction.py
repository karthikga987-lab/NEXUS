
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any


OLLAMA_URL = os.getenv(
    "NEXUS_OLLAMA_URL",
    "http://localhost:11434/api/chat",
)

OLLAMA_MODEL = os.getenv(
    "NEXUS_OLLAMA_MODEL",
    "qwen3:8b",
)

EVENT_TYPES = {
    "product_launch",
    "feature_launch",
    "feature_change",
    "feature_removal",
    "pricing_change",
    "experiment",
    "strategic_decision",
    "partnership",
    "acquisition",
    "market_entry",
    "market_exit",
    "incident",
    "other",
}


logger = logging.getLogger(__name__)


EVENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "event_type": {"type": "string", "enum": sorted(EVENT_TYPES)},
                    "title": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "event_date": {"type": ["string", "null"]},
                    "stated_reason": {"type": ["string", "null"]},
                    "outcome_summary": {"type": ["string", "null"]},
                    "extraction_confidence": {"type": "number"},
                    "evidence_quote": {"type": "string"},
                    "field_quotes": {
                        "type": "object",
                        "properties": {
                            "product_name": {"type": "string"},
                            "event_date": {"type": ["string", "null"]},
                            "stated_reason": {"type": ["string", "null"]},
                            "outcome_summary": {"type": ["string", "null"]},
                        },
                        "required": [
                            "product_name",
                            "event_date",
                            "stated_reason",
                            "outcome_summary",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "product_name",
                    "event_type",
                    "title",
                    "description",
                    "event_date",
                    "stated_reason",
                    "outcome_summary",
                    "extraction_confidence",
                    "evidence_quote",
                    "field_quotes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}


EXTRACTION_PROMPT = """

EXTRACTION EXAMPLES:

POSITIVE EXAMPLE

Source:
"Acme launched Project Nova on March 12, 2025.
Project Nova allows customers to organize their workspaces."

Correct extraction:
{
  "events": [
    {
      "product_name": "Project Nova",
      "event_type": "product_launch",
      "title": "Project Nova launched",
      "description": null,
      "event_date": "2025-03-12",
      "stated_reason": null,
      "outcome_summary": null,
      "extraction_confidence": 0.9,
      "evidence_quote": "Acme launched Project Nova on March 12, 2025.",
      "field_quotes": {
        "product_name": "Acme launched Project Nova on March 12, 2025.",
        "event_date": "March 12, 2025",
        "stated_reason": null,
        "outcome_summary": null
      }
    }
  ]
}

Why this is correct:
- evidence_quote proves the launch actually happened.
- product_name quotation contains the product name.
- event_date uses YYYY-MM-DD format.
- The date quotation is copied exactly from the source.
- No unsupported reason or outcome is invented.

NEGATIVE EXAMPLE

Source:
"Acme offers Project Nova. Customers can organize their workspaces."

Correct extraction:
{
  "events": []
}

Why this is correct:
- The source describes a current product capability.
- It does not document a launch, update, removal, or other completed event.
- Do not invent a historical event from a product description.

You are an evidence-first product intelligence extraction system.

Extract product events ONLY from the supplied source text.

CORE PRINCIPLE:
A description of a product's current capabilities is NOT automatically
evidence of a product event.

A product event must describe an identifiable completed action or change.
Do not convert ordinary product descriptions, feature lists, current
availability, subscription descriptions, or marketing statements into
historical events.

GENERAL RULES:
1. Never invent facts, dates, reasons, or outcomes.
2. Use only the allowed event_type values.
3. product_name must be explicitly identifiable in the source.
4. Every event must have an exact supporting quotation.
5. Copy quotations character-for-character.
6. Do not infer causation from chronological sequence.
7. If a field is unknown or unsupported, return JSON null.
8. Return an empty events array if no valid event exists.
9. Never write "null" as a string.
10. Return only valid JSON.
11. A current product capability is not a launch or change merely
    because it is described on a company website.
12. Do not infer that a feature is new from words such as
    "enjoy", "watch", "use", "discover", "download", or "available".
13. Do not treat a product's current price as evidence of a pricing
    change unless the source explicitly documents a price change.
14. Do not treat a supported device list as a product launch.
15. Do not treat a general product description as an announcement.

EVENT CLASSIFICATION:
16. product_launch: a genuinely new standalone product is introduced.
17. feature_launch: a genuinely new standalone feature is introduced.
18. feature_change: an existing product or feature is updated,
    expanded, redesigned, or materially changed.
19. A newly introduced subscription tier, ad-supported plan,
    household plan, or account option within an existing product
    is generally feature_change, not product_launch or feature_launch.
20. feature_removal: an existing product or feature is removed.
21. pricing_change: an explicit price or subscription-plan price
    change takes effect.
22. market_entry: a product or service becomes available in a
    new geographic market.
23. market_exit: a product or service leaves a geographic market.
24. Do not classify every announcement as a launch.
25. An update to an existing subscription plan is generally
    feature_change unless the source establishes another event type.
26. A statement that a feature currently exists does not establish
    when it was introduced or changed.
27. A statement that a product is currently available does not
    establish a launch event.
28. A completed introduction, release, rollout, launch, removal,
    or material change may qualify even when no event date is given.
29. If the source does not establish an actual completed change,
    return no event.

DATE RULES:
30. event_date must be an explicitly stated event date.
31. Do not use the article publication date as the event date.
32. A date appearing in an article heading or opening publication
    timestamp does not by itself establish an event date.
33. The date quotation must explicitly connect the date to the event.
34. Do not infer a date from context.
35. Return YYYY-MM-DD only for a complete, unambiguous date.
36. Partial dates such as "June 2025" must produce null.
37. Future plans are not completed events.
38. If only the article publication date is available, return null.

REASON RULES:
39. stated_reason must explain WHY the company made the decision
    or introduced the change.
40. A description of what changed is not a reason.
41. Phrases such as "with our updated plan" do not establish
    a decision rationale by themselves.
42. Only return a reason when the source explicitly expresses
    rationale, such as "because", "in response to", "to address",
    or an equally clear explanation.
43. The reason quotation must independently support the reason.
44. The reason summary must accurately reflect that quotation.
45. If no explicit rationale is present, return null.

OUTCOME RULES:
46. outcome_summary must describe an explicitly supported result,
    availability, or measured outcome.
47. Do not turn a future intention into a completed outcome.
48. The outcome quotation must independently support the outcome.
49. If a source says something is available now but will expand
    elsewhere later, report only the currently available part.
50. Do not describe planned future availability as completed.
51. Use a meaningful phrase or sentence, not a single vague word
    such as "available", "launched", or "updated".
52. The outcome summary must accurately reflect its quotation.
53. If no sufficiently specific outcome can be quoted, return null.

ADDITIONAL OUTCOME EXCLUSIONS:
- Product specifications, model sizes, parameter counts, technical
  architecture, intended use, target markets, and feature descriptions
  are not outcomes by themselves.
- Statements defining what a product IS (for example, "is a 32
  billion-parameter model") describe the product, not a result.
- Phrases such as "built for", "designed for", "intended to",
  "supports", "provides", and "is powered by" describe capabilities
  or intended use; do not classify them as outcomes by themselves.
- Do not copy the product description into outcome_summary merely
  because it appears next to a launch announcement.
- A product launch may be a valid event while outcome_summary remains
  null. Keep the event and outcome fields separate.
- Return an outcome only when the source documents a result, measured
  impact, completed availability, adoption, or another concrete
  consequence of the event.

CRITICAL EVIDENCE QUOTATION RULES:
54. evidence_quote must prove that an actual completed event happened.
55. Prefer the shortest exact source-text fragment that proves
    the completed event.
56. Do not select a general product-description sentence when
    another sentence explicitly establishes that an update,
    launch, release, or change became available.
57. Do not include a future rollout clause in evidence_quote.
58. If a sentence contains both completed and future information,
    quote only the exact completed clause as a substring.
59. For example, if the source says:
    "The update is now available in Ireland and will rollout
    in all markets this fall."
    use this exact evidence_quote:
    "The update is now available in Ireland"
60. The evidence_quote must prove a completed event.
61. If no completed event can be established, do not extract it.
62. Phrases such as "made its new subscription offering available"
    and "made the ad-supported plan available" establish completed
    availability when stated as completed actions.
63. Do not use phrases such as "is available" or "are available"
    alone as proof of a historical launch or change.
64. Do not use a current feature description as evidence of
    when or how that feature was introduced.

FIELD QUOTATION RULES:
65. field_quotes.product_name must contain the product name.
66. field_quotes.event_date must quote the original date wording.
67. field_quotes.stated_reason must quote the stated reason.
68. field_quotes.outcome_summary must quote the outcome.
69. If a field is null, its corresponding field_quotes value
    must also be null.
70. Never reuse an unrelated quotation for a field.
71. Every non-null field quotation must occur exactly in the source.
72. Each field summary must be supported by its own quotation.

Allowed event_type values:
product_launch, feature_launch, feature_change, feature_removal,
pricing_change, experiment, strategic_decision, partnership,
acquisition, market_entry, market_exit, incident, other.

Return this structure:
{
  "events": [
    {
      "product_name": "string",
      "event_type": "feature_change",
      "title": "string",
      "description": null,
      "event_date": null,
      "stated_reason": null,
      "outcome_summary": "string or null",
      "extraction_confidence": 0.7,
      "evidence_quote": "short exact completed-event quotation",
      "field_quotes": {
        "product_name": "exact source quotation",
        "event_date": null,
        "stated_reason": null,
        "outcome_summary": "exact source quotation or null"
      }
    }
  ]
}
"""


class ExtractionError(Exception):
    """Raised when event extraction fails."""


def _ask_ollama(source_text: str) -> dict[str, Any]:
    """Send source text to Ollama and require the documented JSON shape."""

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": EVENT_RESPONSE_SCHEMA,
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": 2048,
        },
        "messages": [
            {
                "role": "system",
                "content": EXTRACTION_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Extract only distinct product events explicitly "
                    "supported by the source. Do not repeat events. "
                    "Return exactly one JSON object with an events array. "
                    "If there are no qualifying events, return "
                    "{\"events\": []}.\n\n"
                    "<SOURCE>\n"
                    + source_text
                    + "\n</SOURCE>"
                ),
            },
        ],
    }

    last_error: Exception | None = None

    for attempt in range(2):
        request_payload = dict(payload)
        request_payload["options"] = {
            **payload["options"],
            "num_predict": 2048 if attempt == 0 else 4096,
        }

        done_reason = "unavailable"
        content_length = 0

        request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))

            if not isinstance(result, dict):
                raise ExtractionError(
                    "Ollama returned an invalid response object."
                )

            done_reason = str(result.get("done_reason", "not provided"))

            message = result.get("message")
            if not isinstance(message, dict):
                raise ExtractionError(
                    "Ollama response did not contain a message object."
                )

            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ExtractionError(
                    "Ollama returned an empty event-extraction response."
                )

            content_length = len(content)
            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise ExtractionError("Model returned an invalid JSON object.")

            if not isinstance(parsed.get("events"), list):
                keys = sorted(parsed.keys())
                raise ExtractionError(
                    "Model response must contain an events array; "
                    f"received top-level keys: {keys}."
                )

            if attempt > 0:
                logger.info(
                    "Event extraction succeeded on retry with "
                    "num_predict=4096 (done_reason=%s, response_chars=%s).",
                    done_reason,
                    content_length,
                )

            return parsed

        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                body = ""

            last_error = ExtractionError(
                f"Ollama returned HTTP {exc.code} at {OLLAMA_URL}. "
                f"Response: {body or exc.reason}"
            )
            if attempt == 0 and exc.code in {500, 502, 503, 504}:
                logger.warning(
                    "Ollama returned HTTP %s during event extraction; "
                    "retrying with a larger output budget.",
                    exc.code,
                )
                time.sleep(2)
                continue
            raise last_error from exc

        except urllib.error.URLError as exc:
            last_error = ExtractionError(
                f"Could not connect to Ollama at {OLLAMA_URL}: {exc}"
            )
            if attempt == 0:
                logger.warning(
                    "Ollama connection failed during event extraction; "
                    "retrying once: %s",
                    exc,
                )
                time.sleep(2)
                continue
            raise last_error from exc

        except (json.JSONDecodeError, KeyError, TypeError, ExtractionError) as exc:
            last_error = (
                exc if isinstance(exc, ExtractionError)
                else ExtractionError(
                    "Ollama returned an invalid extraction response."
                )
            )
            if attempt == 0:
                logger.warning(
                    "Invalid event-extraction response; retrying with "
                    "num_predict=4096 "
                    "(done_reason=%s, response_chars=%s): %s",
                    done_reason,
                    content_length,
                    last_error,
                )
                time.sleep(2)
                continue

            logger.error(
                "Event extraction failed after retry "
                "(done_reason=%s, response_chars=%s).",
                done_reason,
                content_length,
            )
            raise last_error from exc

    raise ExtractionError(f"Event extraction failed after retry: {last_error}")

def _is_exact_quote(quote: Any, source_text: str) -> bool:
    """Return True only when the exact quotation occurs in the source."""

    return (
        isinstance(quote, str)
        and bool(quote.strip())
        and quote in source_text
    )


def _meaningful_words(value: str) -> set[str]:
    """Return meaningful normalized words for conservative quote matching."""

    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "been",
        "by", "for", "from", "has", "have", "in", "into",
        "is", "it", "its", "of", "on", "or", "our", "that",
        "the", "their", "this", "to", "was", "were", "we",
        "will", "with", "you", "your",
    }

    words = re.findall(r"[a-z0-9]+", value.lower())

    return {
        word
        for word in words
        if len(word) > 2 and word not in stop_words
    }


def _is_supported_by_quote(
    value: Any,
    quote: Any,
    source_text: str,
) -> bool:
    """
    Check that a field summary is meaningfully supported by its quote.

    This is a conservative lexical consistency check, not a semantic
    proof. Exact source quotation validation remains mandatory.
    """

    if not isinstance(value, str) or not value.strip():
        return False

    if not _is_exact_quote(quote, source_text):
        return False

    value_words = _meaningful_words(value)
    quote_words = _meaningful_words(quote)

    if len(value_words) < 2:
        return False

    overlap = value_words.intersection(quote_words)

    return len(overlap) >= 2 and (
        len(overlap) / len(value_words)
    ) >= 0.4


def _normalize_event_type(
    event_type: str,
    title: str,
    evidence_quote: str,
) -> str:
    """
    Correct subscription-tier classification within an existing product.
    """

    if event_type != "feature_launch":
        return event_type

    combined_text = f"{title} {evidence_quote}"

    subscription_patterns = (
        r"\bsubscription\s+(?:offering|plan|tier)\b",
        r"\b(?:ad-supported|ad supported)\s+"
        r"(?:subscription\s+)?(?:offering|plan|tier)\b",
        r"\b(?:family|student|basic|premium)\s+"
        r"(?:subscription\s+)?(?:plan|tier)\b",
    )

    if any(
        re.search(pattern, combined_text, flags=re.IGNORECASE)
        for pattern in subscription_patterns
    ):
        return "feature_change"

    return event_type


def _is_specific_outcome(
    outcome_summary: Any,
    outcome_quote: Any,
    source_text: str,
) -> bool:
    """
    Reject vague outcomes and require a supporting exact quotation.

    A summary containing both completed results and future plans is
    rejected because the entire summary cannot be classified as a
    completed outcome.
    """

    if not isinstance(outcome_summary, str):
        return False

    summary = outcome_summary.strip()

    if len(summary) < 15 or len(summary.split()) < 3:
        return False

    if summary.lower() in {
        "available",
        "launched",
        "updated",
        "released",
        "introduced",
        "announced",
        "rolled out",
    }:
        return False

    future_phrases = (
        "would launch",
        "will launch",
        "plans to launch",
        "planned to launch",
        "intends to launch",
        "will be available",
        "will roll out",
        "will rollout",
        "will become available",
        "will be released",
        "is expected to launch",
        "is expected to be available",
        "coming soon",
    )

    normalized_summary = summary.lower()

    if any(
        phrase in normalized_summary
        for phrase in future_phrases
    ):
        return False

    # A product's technical definition or intended capability is not
    # an outcome, even when the wording is copied exactly from source.
    product_description_patterns = (
        r"\bis\s+(?:a|an)\s+.{0,100}\b(?:model|platform|"
        r"software|system|tool|chip|device|service|product)\b",
        r"\b(?:built|designed|intended|developed)\s+for\b",
        r"\b(?:provides?|supports?|powered)\s+(?:by|.{1,100})\b",
        r"\b(?:features?|offers?)\s+(?:a|an|the)\b",
    )

    if any(
        re.search(pattern, normalized_summary, flags=re.IGNORECASE)
        for pattern in product_description_patterns
    ):
        return False

    return _is_supported_by_quote(
        summary,
        outcome_quote,
        source_text,
    )

def _completed_event_quote_fragment(
    quote: Any,
    source_text: str,
) -> str | None:
    """
    Return an exact source substring proving a completed event.

    Future rollout statements are excluded. When the quote contains
    introductory sentences before the completed event, retain only
    the sentence containing the completed-event evidence.
    """

    if not _is_exact_quote(quote, source_text):
        return None

    normalized = quote.lower()

    future_phrases = (
        "would launch",
        "will launch",
        "plans to launch",
        "planned to launch",
        "intends to launch",
        "will be available",
        "will roll out",
        "will rollout",
        "will become available",
        "will be released",
        "is expected to launch",
        "is expected to be available",
        "coming soon",
    )

    future_positions = [
        normalized.find(phrase)
        for phrase in future_phrases
        if normalized.find(phrase) >= 0
    ]

    candidate = quote

    if future_positions:
        candidate = quote[:min(future_positions)]
        candidate = candidate.rstrip(" \t\r\n,;:-")

        candidate = re.sub(
            r"\s+(and|but|or)$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).rstrip(" \t\r\n,;:-")

    if not candidate or not _is_exact_quote(candidate, source_text):
        return None

    completed_phrases = (
        "became available",
        "was launched",
        "has launched",
        "launches today",
        "launched today",
        "launches now",
        "launched",
        "was released",
        "has released",
        "released",
        "rolled out",
        "was rolled out",
        "has rolled out",
        "began rolling out",
        "started rolling out",
        "went live",
        "is now available",
        "are now available",
        "was introduced",
        "has introduced",
        "introduced",
        "introduces",
        "announced the launch",
        "announced the release",
        "announced the introduction",
        "announced the rollout",
        "unveiled",
        "unveils",
        "revealed",
        "reveals",
        "debuted",
        "was debuted",
    )

    candidate_normalized = candidate.lower()

    # A statement that a company "announced that a feature would launch"
    # records a future plan, not a completed product event. Only treat the
    # bare verbs "announced/announces" as completed announcement evidence
    # when the quote contains no future-plan clause. Explicit phrases such as
    # "announced the launch" remain eligible in either case.
    eligible_completed_phrases = completed_phrases
    if not future_positions:
        eligible_completed_phrases = completed_phrases + (
            "announced",
            "announces",
        )

    completed_positions = [
        candidate_normalized.find(phrase)
        for phrase in eligible_completed_phrases
        if candidate_normalized.find(phrase) >= 0
    ]

    made_available_match = re.search(
        r"\bmade\b[^.!?\r\n]{0,250}\bavailable\b",
        candidate,
        flags=re.IGNORECASE,
    )

    if completed_positions:
        event_position = min(completed_positions)

        # Keep only the sentence containing the completed-event phrase.
        sentence_start = max(
            candidate.rfind(".", 0, event_position),
            candidate.rfind("!", 0, event_position),
            candidate.rfind("?", 0, event_position),
            candidate.rfind("\n", 0, event_position),
        ) + 1

        candidate = candidate[sentence_start:].strip()

    elif made_available_match:
        event_position = made_available_match.start()

        sentence_start = max(
            candidate.rfind(".", 0, event_position),
            candidate.rfind("!", 0, event_position),
            candidate.rfind("?", 0, event_position),
            candidate.rfind("\n", 0, event_position),
        ) + 1

        candidate = candidate[sentence_start:].strip()

    else:
        return None

    if not candidate or not _is_exact_quote(candidate, source_text):
        return None

    return candidate


def _is_completed_event_quote(
    quote: Any,
    source_text: str,
) -> bool:
    """Check that the evidence quote describes a completed event."""

    return (
        _completed_event_quote_fragment(
            quote,
            source_text,
        )
        is not None
    )


def _date_from_quote(date_quote: str) -> date | None:
    """Parse a complete, unambiguous date from source wording."""

    if not isinstance(date_quote, str):
        return None

    value = date_quote.strip()

    formats = (
        "%B %d, %Y",
        "%B %d %Y",
        "%d %B %Y",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%b %d %Y",
        "%d %b %Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def _date_quote_supports_event(
    date_quote: str,
    evidence_quote: str,
) -> bool:
    """Require the date quotation to occur in the event evidence."""

    if not isinstance(date_quote, str):
        return False

    if not isinstance(evidence_quote, str):
        return False

    date_value = date_quote.strip().lower()
    evidence_value = evidence_quote.strip().lower()

    if not date_value or not evidence_value:
        return False

    return date_value in evidence_value


def _validate_event_date(
    event_date: Any,
    date_quote: Any,
    source_text: str,
    evidence_quote: Any = None,
) -> str | None:
    """
    Validate a complete date against its exact source quotation.

    The original three-argument interface remains supported.
    """

    if not isinstance(event_date, str):
        return None

    if not isinstance(date_quote, str):
        return None

    if not _is_exact_quote(date_quote, source_text):
        return None

    supporting_quote = (
        evidence_quote
        if isinstance(evidence_quote, str)
        else source_text
    )

    if not _date_quote_supports_event(
        date_quote,
        supporting_quote,
    ):
        return None

    try:
        normalized_date = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        return None

    if normalized_date.isoformat() != event_date:
        return None

    quoted_date = _date_from_quote(date_quote)

    if quoted_date is None:
        return None

    if quoted_date != normalized_date:
        return None

    return normalized_date.isoformat()


def _is_explicit_reason_quote(
    quote: Any,
    source_text: str,
) -> bool:
    """Accept exact quotations that explicitly express rationale."""

    if not _is_exact_quote(quote, source_text):
        return False

    normalized = quote.lower()

    reason_indicators = (
        "because",
        "due to",
        "in response to",
        "in order to",
        "to address",
        "to solve",
        "to improve",
        "to reduce",
        "to increase",
        "to help",
        "so that",
        "in an effort to",
        "our goal is",
        "our aim is",
        "the reason",
        "responding to",
        "as a result of",
    )

    return any(
        indicator in normalized
        for indicator in reason_indicators
    )


def validate_extracted_event(
    event: dict[str, Any],
    source_text: str,
    source_id: str,
    company_id: str,
) -> dict[str, Any] | None:
    """Validate an extracted event against its original source."""

    if not isinstance(event, dict):
        return None

    if not isinstance(source_text, str) or not source_text:
        return None

    if not isinstance(source_id, str) or not source_id.strip():
        return None

    if not isinstance(company_id, str) or not company_id.strip():
        return None

    evidence_quote = _completed_event_quote_fragment(
        event.get("evidence_quote"),
        source_text,
    )

    # Some company pages put the completed action in an announcement
    # headline while the model selects the descriptive sentence below it.
    # Accept the headline only when it is itself an exact source substring
    # and contains a recognized completed-event verb.
    if evidence_quote is None:
        evidence_quote = _completed_event_quote_fragment(
            event.get("title"),
            source_text,
        )

    if evidence_quote is None:
        return None

    product_name = event.get("product_name")
    event_type = event.get("event_type")
    title = event.get("title")

    if not all(
        isinstance(value, str) and value.strip()
        for value in (product_name, event_type, title)
    ):
        return None

    if event_type not in EVENT_TYPES:
        return None

    event_type = _normalize_event_type(
        event_type=event_type,
        title=title,
        evidence_quote=evidence_quote,
    )

    field_quotes = event.get("field_quotes")

    if not isinstance(field_quotes, dict):
        return None

    product_quote = field_quotes.get("product_name")

    if (
        not _is_exact_quote(product_quote, source_text)
        or product_name.lower() not in product_quote.lower()
    ):
        return None

    event_date = _validate_event_date(
        event_date=event.get("event_date"),
        date_quote=field_quotes.get("event_date"),
        source_text=source_text,
        evidence_quote=evidence_quote,
    )

    stated_reason = event.get("stated_reason")
    reason_quote = field_quotes.get("stated_reason")

    if stated_reason is not None:
        if (
            not isinstance(stated_reason, str)
            or not _is_explicit_reason_quote(
                reason_quote,
                source_text,
            )
            or not _is_supported_by_quote(
                stated_reason,
                reason_quote,
                source_text,
            )
        ):
            stated_reason = None

    outcome_summary = event.get("outcome_summary")
    outcome_quote = field_quotes.get("outcome_summary")

    if not _is_specific_outcome(
        outcome_summary=outcome_summary,
        outcome_quote=outcome_quote,
        source_text=source_text,
    ):
        outcome_summary = None

    description = event.get("description")

    if (
        not isinstance(description, str)
        or description.strip().lower() in {"", "null", "none"}
        or not _is_supported_by_quote(
            description,
            evidence_quote,
            source_text,
        )
    ):
        description = None

    try:
        confidence = float(event.get("extraction_confidence"))

        if not 0.0 <= confidence <= 1.0:
            confidence = None

    except (ValueError, TypeError):
        confidence = None

    return {
        "company_id": company_id,
        "product_name": product_name.strip(),
        "event_type": event_type,
        "title": title.strip(),
        "description": description,
        "event_date": event_date,
        "stated_reason": stated_reason,
        "outcome_summary": outcome_summary,
        "evidence_status": "documented",
        "extraction_confidence": confidence,
        "source_ids": [source_id],
        "evidence_quote": evidence_quote,
    }


def extract_events(
    source_text: str,
    source_id: str,
    company_id: str,
) -> list[dict[str, Any]]:
    """Extract and validate events. This function does not save to the DB."""

    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("Source text cannot be empty.")

    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("A source ID is required.")

    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("A company ID is required.")

    result = _ask_ollama(source_text)

    raw_events = result.get("events", [])

    if not isinstance(raw_events, list):
        raise ExtractionError(
            "The model did not return an events array."
        )

    validated_events = []

    for event in raw_events:
        validated = validate_extracted_event(
            event=event,
            source_text=source_text,
            source_id=source_id,
            company_id=company_id,
        )

        if validated is not None:
            validated_events.append(validated)

    return validated_events