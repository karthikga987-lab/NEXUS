import json
import logging
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Any


logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv(
    "NEXUS_OLLAMA_URL",
    "http://localhost:11434/api/chat",
)
OLLAMA_MODEL = os.getenv(
    "NEXUS_OLLAMA_MODEL",
    "qwen3:8b",
)

VERIFICATION_TIMEOUT = 180
VERIFICATION_BATCH_SIZE = 8

IMPORTANT_QUALIFIERS = {
    "additional",
    "approximately",
    "about",
    "around",
    "at least",
    "at most",
    "up to",
    "more than",
    "less than",
    "planned",
    "proposed",
    "expected",
    "potential",
    "eligible",
    "selected",
    "only",
    "first",
    "final",
    "initial",
    "limited",
    "temporarily",
    "permanently",
    "voluntarily",
    "reportedly",
    "allegedly",
}

VERIFICATION_PROMPT = """
You are an independent evidence verifier for NEXUS.

You receive multiple independent verification requests. Each request
contains a claim and one original source passage.

For EACH request:
1. Use only that request's source passage and source company context.
2. Determine whether the passage supports the COMPLETE factual meaning
   of the claim.
3. Company context may clarify attribution, but cannot prove an event.
3a. First distinguish direct, partial, indirect, contradictory, and absent
    support. Only direct support for the complete claim may be returned as
    supported=true. Reject partial, indirect, contradictory, or absent support.
3b. The claim and supporting quotation must describe the SAME subject.
3c. A statement about a company's platform does not prove a statement about a specific model. A statement about a partnership does not prove that a specific product was used or adopted. A statement about a company does not automatically prove a statement about its product.
3d. Never transfer actions such as adoption, deployment, integration, launch or use between a company, platform, partner and model.
3e. Related products appearing in the same passage is not sufficient evidence. Reject the claim unless the quoted passage directly connects the named subject to the claimed action or property.
4. Reject unsupported dates, numbers, prices, counts and qualifiers.
5. Preserve material qualifiers such as approximately, planned,
   expected, more than, at least, selected and eligible. Reject a claim
   that omits a qualifier which materially narrows the same event or figure.
   When a source sentence contains a potentially relevant qualifier, the
   supporting quotation must include enough contiguous context to show
   whether that qualifier applies to the claim.
6. Do not infer causation from chronology or correlation.
7. Reject a claim if only part of it is supported.
8. Do not combine evidence from separate requests or passages.
9. If ambiguous, return supported=false.
10. If supported, return a short, verbatim, contiguous quotation from
    that exact source passage. Include the relevant qualifier in the quote.
11. Never invent, rewrite or paraphrase the quotation.
12. Copy request_id, claim_index and source_id exactly.
13. Return one result for every request.

Return only valid JSON:
{
  "verifications": [
    {
      "request_id": 0,
      "claim_index": 0,
      "source_id": "exact source ID",
      "supported": true,
      "supporting_quote": "Exact contiguous quotation"
    }
  ]
}
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _extract_numbers(text: str) -> set[str]:
    return {
        value.replace(",", "")
        for value in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", text)
    }


def _numbers_are_supported(statement: str, quote: str) -> bool:
    return _extract_numbers(statement).issubset(
        _extract_numbers(quote)
    )


def _qualifier_tokens(text: str) -> set[str]:
    normalized = _normalize(text)

    return {
        qualifier
        for qualifier in IMPORTANT_QUALIFIERS
        if re.search(
            rf"(?<!\w){re.escape(qualifier)}(?!\w)",
            normalized,
        )
    }


def _qualifiers_are_preserved(statement: str, quote: str) -> bool:
    """Require every material qualifier asserted by a claim in its quote.

    The quote can include additional context, so exact set equality was too
    strict: an unrelated qualifier elsewhere in a contiguous quotation should
    not automatically invalidate an otherwise supported claim. The verifier
    prompt separately requires the model to reject claims that omit a
    qualifier materially narrowing the same event or figure.
    """
    statement_qualifiers = _qualifier_tokens(statement)
    quote_qualifiers = _qualifier_tokens(quote)
    return statement_qualifiers.issubset(quote_qualifiers)



def _context_has_unrepresented_qualifier(
    statement: str,
    source_text: str,
    quote: str,
) -> bool:
    """
    Detect qualifiers omitted from the source sentence supporting
    a claim. Do not treat adjacent sentences as qualifiers.
    """

    match = re.search(
        re.escape(quote),
        source_text,
        flags=re.IGNORECASE,
    )

    if not match:
        return False

    boundary_pattern = re.compile(r"[.!?\n]+")

    sentence_start = 0
    sentence_end = len(source_text)

    # Find the beginning of the sentence containing the quotation.
    for boundary in boundary_pattern.finditer(source_text):
        if boundary.end() <= match.start():
            sentence_start = boundary.end()
        else:
            break

    matched_quote = source_text[match.start():match.end()]

    # If the quotation already includes its sentence-ending
    # punctuation, do not include the next sentence.
    if matched_quote.rstrip().endswith((".", "?", "!")):
        sentence_end = match.end()
    else:
        for boundary in boundary_pattern.finditer(
            source_text,
            match.end(),
        ):
            sentence_end = boundary.end()
            break

    sentence_context = source_text[
        sentence_start:sentence_end
    ].strip()

    return not _qualifier_tokens(sentence_context).issubset(
        _qualifier_tokens(statement)
    )


def _quote_exists(quote: str, source_text: str) -> bool:
    if not isinstance(quote, str) or not quote.strip():
        return False

    if not isinstance(source_text, str) or not source_text.strip():
        return False

    return _normalize(quote) in _normalize(source_text)


def _find_exact_quote(
    statement: str,
    source_text: str,
) -> str | None:
    if not statement.strip() or not source_text.strip():
        return None

    words = re.split(r"\s+", statement.strip())
    pattern = r"\s+".join(re.escape(word) for word in words)

    match = re.search(
        pattern,
        source_text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return source_text[match.start():match.end()]


def _find_company_contextual_quote(
    statement: str,
    source_text: str,
    company_name: str | None,
) -> str | None:
    """
    Permit trusted source metadata to clarify company attribution.

    The remaining claim wording must still match contiguously in the
    original passage.
    """
    if not isinstance(company_name, str) or not company_name.strip():
        return None

    direct = _find_exact_quote(statement, source_text)

    if direct:
        return direct

    candidate = statement

    company_words = sorted(
        company_name.split(),
        key=len,
        reverse=True,
    )

    for word in company_words:
        word = word.strip()

        if len(word) <= 2:
            continue

        if re.search(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            source_text,
            flags=re.IGNORECASE,
        ):
            continue

        candidate = re.sub(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            " ",
            candidate,
            flags=re.IGNORECASE,
        )

    candidate = re.sub(r"\s+", " ", candidate).strip()
    candidate = re.sub(r"\s+([,.;:])", r"\1", candidate)

    if not candidate:
        return None

    return _find_exact_quote(candidate, source_text)


def _passages(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        return [
            passage
            for passage in value
            if isinstance(passage, str) and passage.strip()
        ]

    return []


def _call_ollama_batch(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    if not items:
        return [], None

    requests = [
        {
            "request_id": item["request_id"],
            "claim_index": item["claim_index"],
            "claim_type": item["type"],
            "claim": item["statement"],
            "source_id": item["source_id"],
            "source_company_context": (
                item.get("source_company_name") or "Not available"
            ),
            "source_passage": item["source_text"],
        }
        for item in items
    ]

    user_message = (
        "Verify every request independently. Do not mix evidence "
        "between requests.\n\n"
        "VERIFICATION_REQUESTS:\n"
        + json.dumps(requests, ensure_ascii=False)
    )

    payload = {
        "model": OLLAMA_MODEL,
        "think": False,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": VERIFICATION_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=VERIFICATION_TIMEOUT,
        ) as response:
            raw = json.loads(response.read().decode("utf-8"))

        parsed = json.loads(
            raw.get("message", {}).get("content", "")
        )

    except urllib.error.HTTPError as exc:
        return [], f"Ollama returned HTTP {exc.code} during verification."
    except urllib.error.URLError:
        return [], "Evidence verification could not connect to Ollama."
    except (TimeoutError, socket.timeout):
        return [], "Evidence verification timed out."
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return [], "Evidence verification received an invalid response."

    if not isinstance(parsed, dict):
        return [], "Evidence verifier returned an invalid response object."

    entries = parsed.get("verifications")

    if not isinstance(entries, list):
        return [], "Evidence verifier returned no valid verifications list."

    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
    ], None


def verify_claim_citations(
    claims: list[dict[str, Any]],
    source_text_by_id: dict[str, Any],
    source_context_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[tuple[int, str], dict[str, Any]], str | None]:
    """Verify candidate claim/source pairs against original source passages.

    Supported source input formats:
        {source_id: "one passage"}
        {source_id: ["passage one", "passage two"]}

    A quotation must exist in one original passage. It cannot be
    assembled across passage or chunk boundaries.

    The public signature and return format remain compatible with
    the existing proposal-analysis pipeline.
    """
    if not isinstance(claims, list):
        return {}, "Invalid claims supplied to the evidence verifier."

    if not isinstance(source_text_by_id, dict):
        return {}, "Invalid source text supplied to the evidence verifier."

    source_context_by_id = source_context_by_id or {}

    validated: dict[tuple[int, str], dict[str, Any]] = {}
    semantic_requests: list[dict[str, Any]] = []
    rejection_counts: dict[str, int] = {}
    batch_errors: list[str] = []

    def record_rejection(reason: str) -> None:
        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue

        statement = claim.get("statement")
        source_ids = claim.get("candidate_source_ids", [])

        if not isinstance(statement, str) or not statement.strip():
            continue

        if not isinstance(source_ids, list):
            continue

        for source_id in dict.fromkeys(source_ids):
            if not isinstance(source_id, str):
                continue

            passages = _passages(source_text_by_id.get(source_id))

            if not passages:
                record_rejection("source_has_no_passages")
                continue

            context = source_context_by_id.get(source_id, {})

            if not isinstance(context, dict):
                context = {}

            pair_key = (claim_index, source_id)

            for passage_index, passage in enumerate(passages):
                item = {
                    "claim_index": claim_index,
                    "statement": statement.strip(),
                    "type": claim.get(
                        "type",
                        "factual_observation",
                    ),
                    "source_id": source_id,
                    "source_text": passage,
                    "source_company_name": context.get(
                        "source_company_name"
                    ),
                    "passage_index": passage_index,
                }

                quote = _find_exact_quote(
                    item["statement"],
                    passage,
                )
                method = "exact_passage_match"

                if not quote:
                    quote = _find_company_contextual_quote(
                        item["statement"],
                        passage,
                        item["source_company_name"],
                    )
                    method = "company_contextual_passage_match"

                if quote:
                    if not _numbers_are_supported(
                        item["statement"],
                        quote,
                    ):
                        record_rejection("numeric_detail_mismatch")
                        semantic_requests.append(item)
                        continue

                    if not _qualifiers_are_preserved(
                        item["statement"],
                        quote,
                    ):
                        record_rejection("qualifier_mismatch")
                        semantic_requests.append(item)
                        continue

                    if _context_has_unrepresented_qualifier(
                        item["statement"],
                        passage,
                        quote,
                    ):
                        record_rejection("qualifier_context_mismatch")
                        semantic_requests.append(item)
                        continue

                    validated[pair_key] = {
                        "source_id": source_id,
                        "supporting_quote": quote,
                        "verification_method": method,
                        "passage_index": passage_index,
                    }
                    break

                semantic_requests.append(item)

    pending_requests = [
        item
        for item in semantic_requests
        if (
            item["claim_index"],
            item["source_id"],
        ) not in validated
    ]

    for request_id, item in enumerate(pending_requests):
        item["request_id"] = request_id

    for batch_start in range(
        0,
        len(pending_requests),
        VERIFICATION_BATCH_SIZE,
    ):
        batch = pending_requests[
            batch_start:batch_start + VERIFICATION_BATCH_SIZE
        ]

        entries, error = _call_ollama_batch(batch)

        if error:
            record_rejection("ollama_batch_error")
            batch_errors.append(error)
            logger.warning("Citation verification batch failed: %s", error)
            continue

        items_by_request_id = {
            item["request_id"]: item
            for item in batch
        }

        seen_request_ids = set()
        returned_request_ids = set()

        for entry in entries:
            request_id = entry.get("request_id")

            if (
                not isinstance(request_id, int)
                or isinstance(request_id, bool)
            ):
                record_rejection("invalid_request_id")
                continue

            candidate = items_by_request_id.get(request_id)

            if candidate is None:
                record_rejection("unknown_request_id")
                continue

            if request_id in seen_request_ids:
                record_rejection("duplicate_request_result")
                continue

            seen_request_ids.add(request_id)
            returned_request_ids.add(request_id)

            if entry.get("claim_index") != candidate["claim_index"]:
                record_rejection("claim_index_mismatch")
                continue

            if entry.get("source_id") != candidate["source_id"]:
                record_rejection("source_id_mismatch")
                continue

            if entry.get("supported") is not True:
                record_rejection("model_rejected_or_uncertain")
                continue

            pair_key = (
                candidate["claim_index"],
                candidate["source_id"],
            )

            if pair_key in validated:
                continue

            quote = entry.get("supporting_quote")
            passage = candidate["source_text"]
            statement = candidate["statement"]

            if not isinstance(quote, str) or not quote.strip():
                record_rejection("missing_supporting_quote")
                continue

            if not _quote_exists(quote, passage):
                record_rejection("quote_not_in_original_passage")
                continue

            if not _numbers_are_supported(statement, quote):
                record_rejection("numeric_detail_mismatch")
                continue

            if not _qualifiers_are_preserved(statement, quote):
                record_rejection("qualifier_mismatch")
                continue

            if _context_has_unrepresented_qualifier(
                statement,
                passage,
                quote,
            ):
                record_rejection("qualifier_context_mismatch")
                continue

            validated[pair_key] = {
                "source_id": candidate["source_id"],
                "supporting_quote": quote,
                "verification_method": (
                    "llm_with_exact_quote_validation"
                ),
                "passage_index": candidate["passage_index"],
            }

        missing_request_ids = (
            set(items_by_request_id) - returned_request_ids
        )

        if missing_request_ids:
            record_rejection("missing_verification_results")

    if rejection_counts:
        logger.info(
            "Citation verification diagnostics: %s",
            json.dumps(rejection_counts, sort_keys=True),
        )

    verification_error = None

    if batch_errors:
        verification_error = (
            "One or more evidence verification batches failed: "
            + "; ".join(dict.fromkeys(batch_errors))
        )
    elif semantic_requests:
        expected_semantic_pairs = {
            (item["claim_index"], item["source_id"])
            for item in semantic_requests
        }
        unresolved_pairs = expected_semantic_pairs - set(validated)

        if unresolved_pairs:
            verification_error = (
                f"Semantic verification did not produce accepted evidence "
                f"for {len(unresolved_pairs)} candidate claim/source pair(s). "
                "These citations were not accepted."
            )

    return validated, verification_error
