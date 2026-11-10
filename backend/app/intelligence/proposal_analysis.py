import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app.intelligence.claim_verification import verify_claim_citations


logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv(
    "NEXUS_OLLAMA_URL",
    "http://localhost:11434/api/chat",
)
OLLAMA_MODEL = os.getenv(
    "NEXUS_OLLAMA_MODEL",
    "llama3.2:3b",
)

OLLAMA_TIMEOUT = 180
PROPOSAL_ANALYSIS_TIMEOUT = 600


PROPOSAL_ANALYSIS_PROMPT = """
You are NEXUS, an evidence-first product decision intelligence assistant.

Analyze the supplied proposal using ONLY the historical evidence provided.

EVIDENCE SCOPES
- INTERNAL: historical evidence belonging to the proposing company.
- EXTERNAL_PUBLIC: public historical evidence belonging to other companies.
- CUSTOMER_FEEDBACK: individual customer signals, not documentary evidence.
- GRAPH_CONTEXT: supplementary historical context, not documentary evidence.

STRICT EVIDENCE RULES
1. Use CONTENT passages as factual evidence. Titles, URLs, metadata and similarity scores are not factual evidence.
2. Every factual observation must be supported by supplied source content.
3. Never invent events, dates, reasons, decision makers, metrics, outcomes or experiments.
4. Never infer causation from chronology or correlation.
5. Do not treat a similarity score as factual confidence.
6. Do not cite customer feedback IDs or graph event IDs as document source IDs.
7. Do not treat customer feedback as documentary proof.
8. Do not treat a hypothesis as a factual observation.
9. Do not use knowledge outside the supplied evidence.
10. Keep internal and external public evidence distinct.
11. A source about another company must not be treated as evidence about the proposing company.
12. If no passage supports a claim, return an empty source_ids list.
13. Do not invent or modify source IDs.
14. Do not put recommendations or predictions in factual claims.
15. Do not invent experiment results or success metrics.
16. Prefer narrow, precisely supported claims.
17. Preserve important dates, numbers and qualifiers.
18. Unsupported historical events must remain explicitly unsupported.

CLAIM CONSTRUCTION RULES
- Keep factual claims as close as possible to the exact wording of the source passage.
- Preserve the grammatical subject of every source statement. Distinguish a specific model from a platform, company, partnership or broader product family.
- Never transfer an action or property from a platform to a model, or from a company or partner to a product.
- Do not infer that a model was deployed, adopted, integrated or used merely because the source discusses it near a deployment or partnership announcement.
- Do not combine adjacent headlines or separate announcements into one factual claim.
- Each factual claim must be directly supportable by one original source passage. If the passage does not establish the complete claim, omit it or label the interpretation as a hypothesis.

PROPOSAL RELEVANCE RULES
19. Identify the actual problem, product area and intended outcome in the proposal.
20. Prioritize evidence directly related to that problem and product area.
21. Do not treat general company history as evidence about the proposal's specific problem.
22. Do not include unrelated historical events merely because they belong to the same company.
23. Distinguish direct evidence from adjacent or contextual information.
24. If no relevant historical evidence exists, explicitly state that limitation.
25. Do not imply that missing evidence means a problem does not exist.
26. Do not present irrelevant evidence as support for proceeding or rejecting the proposal.

CUSTOMER FEEDBACK RULES
27. Feedback is a signal of individual customer experiences, needs, complaints, preferences or requests.
28. Use directly relevant feedback first when evaluating customer needs for the proposal.
29. Related feedback may identify adjacent risks or questions to investigate, but must not be described as direct evidence of the proposal's specific problem.
30. Exclude unrelated feedback from proposal-specific risks and recommendations.
31. Do not treat positive sentiment labels as proof that a requested improvement is unnecessary.
32. Sentiment, feedback type and topic labels are heuristic classifications and may be inaccurate.
33. Preserve the distinction between the original feedback text and its classifier labels.
34. Do not invent customer counts, percentages, trends or prevalence.
35. Do not claim that a small number of examples represents all customers.
36. If feedback URLs appear sample-like or their provenance is unverified, explicitly qualify the feedback as unverified sample-like input.
37. Do not cite feedback as documentary evidence.

GRAPH RULES
38. Graph context is supplementary only.
39. Do not create factual claims from graph context alone.
40. Chronology and stored relationships do not establish causation.

RECOMMENDATION RULES
41. Give a concrete recommendation addressing the actual proposal.
42. Base the recommendation on directly relevant evidence, relevant customer signals and clearly labelled reasoning.
43. Do not let unrelated feedback or unrelated historical events determine the recommendation.
44. Distinguish documented facts, customer signals, hypotheses and unknowns.
45. If evidence is insufficient, recommend a specific validation step.
46. Explain what to investigate, what experiment or comparison to run, and what decision the results would inform.
47. Risks must be specific to the proposal. Label hypotheses clearly.
48. Do not return generic placeholder text.
49. Return only valid JSON.

CLAIM TYPES
Use exactly one of these two values:
- factual_observation
- hypothesis

A factual_observation must be supported by source content.
A hypothesis is an interpretation or testable possibility, not a fact.
Hypotheses should normally have an empty source_ids list unless a source directly supports the historical observation being described.

Return this JSON structure:
{
  "recommendation": "A specific recommendation for this proposal.",
  "risks": ["A proposal-specific risk or clearly labelled hypothesis."],
  "limitations": ["A specific limitation of the available evidence."],
  "claims": [
    {
      "statement": "One atomic factual observation or hypothesis.",
      "type": "factual_observation",
      "source_ids": ["exact supplied source ID"]
    }
  ]
}
"""



PROPOSAL_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string"
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"}
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"}
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "factual_observation",
                            "hypothesis"
                        ]
                    },
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": [
                    "statement",
                    "type",
                    "source_ids"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": [
        "recommendation",
        "risks",
        "limitations",
        "claims"
    ],
    "additionalProperties": False
}

SOURCE_ASSIGNMENT_PROMPT = """
You are the NEXUS source-selection assistant.

You receive multiple claims and a shared collection of evidence passages.

For EACH supplied claim, find evidence passages that directly support
the COMPLETE factual meaning of that claim.

Rules:
1. Use only supplied evidence passages.
2. Copy source IDs exactly.
3. Never invent or modify source IDs.
4. Select a source only when its CONTENT directly supports the complete claim.
5. A source supporting only part of a multi-part claim is insufficient.
6. Do not select a source merely because it discusses the same topic.
7. Dates, numbers, prices, counts and qualifiers must be supported by CONTENT.
8. Preserve additional, planned, expected, approximately, more than,
   at least, selected and eligible.
9. Do not infer causation from chronology or correlation.
10. Keep INTERNAL and EXTERNAL_PUBLIC evidence distinct.
11. A source about another company must not be treated as evidence about
    the proposing company.
12. Name the company described by the source when attribution matters.
13. If no passage supports the complete claim, return an empty source_ids list.
14. Do not rewrite or modify any claim.
15. Return exactly one assignment for every supplied claim index.
16. Copy each claim_index exactly.
17. Do not mix evidence between claims.
18. Return only valid JSON.

Return:
{
  "assignments": [
    {
      "claim_index": 0,
      "source_ids": ["exact source ID"]
    }
  ]
}
"""


class ProposalAnalysisError(Exception):
    """Raised when proposal analysis fails."""


def _normalize_claim_type(value: Any) -> tuple[str, bool]:
    """
    Normalize model-generated claim type variations.

    Returns:
        (normalized_type, was_normalized)

    Unknown or missing types are conservatively classified as hypotheses.
    They are never automatically promoted to factual observations.
    """
    if not isinstance(value, str):
        return "hypothesis", True

    normalized = "_".join(
        value.casefold().strip().replace("-", " ").split()
    )

    factual_aliases = {
        "factual_observation",
        "factual",
        "fact",
        "facts",
        "observation",
        "historical_fact",
        "historical_observation",
        "documented_fact",
        "documented_observation",
    }

    hypothesis_aliases = {
        "hypothesis",
        "hypotheses",
        "inference",
        "interpretation",
        "assumption",
        "possibility",
        "prediction",
        "speculation",
        "testable_hypothesis",
    }

    if normalized in factual_aliases:
        return (
            "factual_observation",
            normalized != "factual_observation",
        )

    if normalized in hypothesis_aliases:
        return "hypothesis", normalized != "hypothesis"

    return "hypothesis", True


def _normalize_claim_types(
    raw_claims: Any,
) -> tuple[list[Any], int]:
    """
    Normalize claim types before source assignment and verification.

    Claim order and indexes are preserved. Invalid claim objects are
    preserved so the verifier's claim indexes remain aligned.
    """
    if not isinstance(raw_claims, list):
        return [], 0

    normalized_claims = []
    normalized_count = 0

    for claim in raw_claims:
        if not isinstance(claim, dict):
            normalized_claims.append(claim)
            continue

        normalized_claim = dict(claim)

        claim_type, was_normalized = _normalize_claim_type(
            normalized_claim.get("type")
        )

        normalized_claim["type"] = claim_type

        if was_normalized:
            normalized_claim["_type_normalized"] = True
            normalized_count += 1
        else:
            normalized_claim["_type_normalized"] = False

        normalized_claims.append(normalized_claim)

    return normalized_claims, normalized_count


def _usable_chunks(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(chunks, list):
        return []

    return [
        item
        for item in chunks
        if isinstance(item, dict)
        and isinstance(item.get("source_id"), str)
        and item["source_id"].strip()
        and isinstance(item.get("chunk_text"), str)
        and item["chunk_text"].strip()
    ]


def _normalize_for_exact_match(text: str) -> str:
    """
    Normalize whitespace and letter case for deterministic matching.

    Punctuation, numbers and qualifiers are preserved.
    """
    return " ".join(text.casefold().split())


def _find_exact_matching_sources(
    statement: str,
    evidence_chunks: list[dict[str, Any]],
    allowed_source_ids: set[str],
) -> list[str]:
    """
    Find sources containing the complete claim as a contiguous passage.

    This is a candidate-discovery step only. The independent citation
    verifier still decides whether the citation is accepted.
    """
    if not isinstance(statement, str) or not statement.strip():
        return []

    normalized_statement = _normalize_for_exact_match(statement)

    if not normalized_statement:
        return []

    matched_source_ids = []

    for item in evidence_chunks:
        if not isinstance(item, dict):
            continue

        source_id = item.get("source_id")
        chunk_text = item.get("chunk_text")

        if (
            not isinstance(source_id, str)
            or source_id not in allowed_source_ids
            or not isinstance(chunk_text, str)
            or not chunk_text.strip()
        ):
            continue

        normalized_chunk = _normalize_for_exact_match(chunk_text)

        if normalized_statement in normalized_chunk:
            matched_source_ids.append(source_id)

    return list(dict.fromkeys(matched_source_ids))


def _call_ollama_json(
    system_prompt: str,
    user_message: str,
    timeout: int = OLLAMA_TIMEOUT,
    response_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "think": False,
        "stream": False,
        "format": response_schema or "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
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
            timeout=timeout,
        ) as response:
            raw = json.loads(response.read().decode("utf-8"))

        parsed = json.loads(
            raw.get("message", {}).get("content", "")
        )

    except urllib.error.HTTPError as exc:
        raise ProposalAnalysisError(
            f"Ollama returned HTTP {exc.code}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ProposalAnalysisError(
            f"Could not connect to Ollama at {OLLAMA_URL}: {exc}"
        ) from exc
    except TimeoutError as exc:
        raise ProposalAnalysisError(
            "Ollama request timed out."
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        raise ProposalAnalysisError(
            "Ollama returned an invalid JSON response."
        ) from exc

    if not isinstance(parsed, dict):
        raise ProposalAnalysisError(
            "Ollama returned an invalid response object."
        )

    return parsed


def _build_evidence_message(
    evidence_chunks: list[dict[str, Any]],
) -> str:
    blocks = []

    for item in evidence_chunks:
        blocks.append(
            f"SOURCE_ID: {item['source_id']}\n"
            f"EVIDENCE_SCOPE: "
            f"{item.get('evidence_scope', 'internal')}\n"
            f"COMPANY: "
            f"{item.get('source_company_name') or 'Not available'}\n"
            f"SOURCE_TITLE: "
            f"{item.get('source_title') or 'Not available'}\n"
            f"CONTENT:\n{item['chunk_text']}"
        )

    return "\n\n".join(blocks)


def _assign_claim_sources(
    raw_claims: Any,
    evidence_chunks: list[dict[str, Any]],
    allowed_source_ids: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Add deterministic exact-text matches, then supplement with AI selection.

    Original valid candidates and deterministic matches are retained
    even if supplementary AI source selection fails.
    """
    if not isinstance(raw_claims, list):
        return [], None

    claims = [
        dict(item) if isinstance(item, dict) else item
        for item in raw_claims
    ]

    # Only send evidence with source IDs authorized for this analysis.
    eligible_chunks = [
        item
        for item in evidence_chunks
        if isinstance(item, dict)
        and item.get("source_id") in allowed_source_ids
    ]

    original_candidates_by_index: dict[int, list[str]] = {}
    assignable_claims = []

    exact_match_count = 0

    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue

        statement = claim.get("statement")
        existing_ids = claim.get("source_ids", [])

        if not isinstance(existing_ids, list):
            existing_ids = []

        original_candidates = list(dict.fromkeys(
            source_id
            for source_id in existing_ids
            if isinstance(source_id, str)
            and source_id in allowed_source_ids
        ))

        exact_matches = _find_exact_matching_sources(
            statement if isinstance(statement, str) else "",
            eligible_chunks,
            allowed_source_ids,
        )

        exact_match_count += len(exact_matches)

        # Keep both original model selections and deterministic matches.
        candidates = list(dict.fromkeys(
            original_candidates + exact_matches
        ))

        original_candidates_by_index[claim_index] = candidates
        claim["source_ids"] = list(candidates)

        if not isinstance(statement, str) or not statement.strip():
            continue

        assignable_claims.append({
            "claim_index": claim_index,
            "claim_type": claim.get(
                "type",
                "hypothesis",
            ),
            "statement": statement.strip(),
        })

    logger.info(
        "Claim source preparation: %d claim(s), "
        "%d exact-text source match(es), "
        "%d eligible source(s).",
        len(assignable_claims),
        exact_match_count,
        len(allowed_source_ids),
    )

    if not assignable_claims:
        return claims, None

    evidence_message = _build_evidence_message(eligible_chunks)

    user_message = (
        "Find supporting evidence for every supplied claim. Inspect "
        "CONTENT, not titles. Preserve qualifiers and company attribution. "
        "Do not mix evidence between claims. Return exactly one assignment "
        "for every claim index.\n\n"
        "CLAIMS:\n"
        f"{json.dumps(assignable_claims, ensure_ascii=False)}\n\n"
        f"SUPPLIED EVIDENCE:\n{evidence_message}"
    )

    try:
        result = _call_ollama_json(
            SOURCE_ASSIGNMENT_PROMPT,
            user_message,
        )
    except ProposalAnalysisError as exc:
        logger.warning(
            "Supplementary source selection failed: %s",
            exc,
        )
        return claims, (
            "Batched supplementary source selection failed. "
            "Original and exact-text candidate citations were retained "
            "for independent verification. "
            f"Details: {exc}"
        )

    assignments = result.get("assignments")

    if not isinstance(assignments, list):
        return claims, (
            "Batched supplementary source selection returned no usable "
            "assignments. Original and exact-text candidate citations "
            "were retained for independent verification."
        )

    assignments_by_index: dict[int, dict[str, Any]] = {}

    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue

        claim_index = assignment.get("claim_index")

        if (
            not isinstance(claim_index, int)
            or isinstance(claim_index, bool)
            or claim_index not in original_candidates_by_index
        ):
            continue

        if claim_index in assignments_by_index:
            continue

        assignments_by_index[claim_index] = assignment

    failed_count = 0
    empty_count = 0

    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue

        original_candidates = original_candidates_by_index.get(
            claim_index,
            [],
        )

        statement = claim.get("statement")

        if not isinstance(statement, str) or not statement.strip():
            continue

        assignment = assignments_by_index.get(claim_index)

        if assignment is None:
            failed_count += 1
            claim["source_ids"] = list(original_candidates)
            continue

        selected_ids = assignment.get("source_ids")

        if not isinstance(selected_ids, list):
            failed_count += 1
            claim["source_ids"] = list(original_candidates)
            continue

        valid_selected = [
            source_id
            for source_id in selected_ids
            if isinstance(source_id, str)
            and source_id in allowed_source_ids
        ]

        if not valid_selected:
            empty_count += 1

        # Never allow the supplementary model to remove deterministic
        # matches or previously valid candidate source IDs.
        claim["source_ids"] = list(dict.fromkeys(
            original_candidates + valid_selected
        ))

    messages = []

    if failed_count:
        messages.append(
            f"Supplementary source selection did not return a usable "
            f"assignment for {failed_count} claim(s). Original and "
            "exact-text candidate citations were retained for verification."
        )

    if empty_count:
        messages.append(
            f"Supplementary source selection found no additional "
            f"candidate sources for {empty_count} claim(s)."
        )

    return claims, "; ".join(messages) or None


def _prepare_verification_claims(
    raw_claims: Any,
    allowed_source_ids: set[str],
) -> list[dict[str, Any]]:
    """
    Preserve claim indexes, including claims without candidate sources.
    """
    if not isinstance(raw_claims, list):
        return []

    prepared = []

    for claim in raw_claims:
        if not isinstance(claim, dict):
            prepared.append({
                "statement": "",
                "type": "hypothesis",
                "candidate_source_ids": [],
            })
            continue

        statement = claim.get("statement", "")
        source_ids = claim.get("source_ids", [])

        if not isinstance(statement, str):
            statement = ""

        if not isinstance(source_ids, list):
            source_ids = []

        normalized_type, _ = _normalize_claim_type(
            claim.get("type")
        )

        prepared.append({
            "statement": statement.strip(),
            "type": normalized_type,
            "candidate_source_ids": list(dict.fromkeys(
                source_id
                for source_id in source_ids
                if isinstance(source_id, str)
                and source_id in allowed_source_ids
            )),
        })

    return prepared


def _deduplicate_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()

    for item in items:
        if not isinstance(item, str):
            continue

        cleaned = item.strip()

        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        result.append(cleaned)

    return result


def _is_placeholder(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    normalized = normalized.strip(" \"'`")

    exact_placeholders = {
        "a concrete recommendation addressing the proposal. distinguish "
        "evidence from hypotheses and include a validation step where "
        "evidence is insufficient.",
        "a specific evidence-grounded risk or clearly labelled hypothesis.",
        "a specific evidence-grounded risk or clearly labelled hypothesis",
        "a specific limitation of the available evidence.",
        "a specific limitation of the available evidence",
        "a specific limitation of available evidence.",
        "a concrete recommendation addressing the proposal.",
        "evidence-grounded recommendation with uncertainty.",
        "recommendation based on the available evidence.",
        "risk or hypothesis, clearly labelled.",
        "limitations of the available evidence.",
        "n/a",
        "none",
        "none.",
        "not available",
        "not available.",
        "unknown",
        "unknown.",
    }

    if normalized in exact_placeholders:
        return True

    return (
        normalized.startswith("insert ")
        or normalized.startswith("your specific recommendation")
        or normalized.startswith("a specific risk or clearly labelled")
        or normalized.startswith("a specific limitation")
        or normalized.startswith("describe a specific")
    )


def _fallback_recommendation(
    title: str,
    description: str,
    internal_count: int,
    external_count: int,
) -> str:
    proposal_context = f"{title.strip()}: {description.strip()}"

    evidence_context = (
        f"The analysis had {internal_count} internal evidence passage(s) "
        f"and {external_count} eligible external public passage(s)."
    )

    return (
        f"For the proposal '{proposal_context}', do not commit to a broad "
        "rollout solely on the basis of historical comparisons. First, "
        "validate the proposal with target users and the proposing "
        "company's own product and operational constraints. Define the "
        "specific user problem, compare the proposed approach with the "
        "current experience, and run a controlled pilot or experiment "
        "that records user behaviour and relevant business outcomes. "
        "Use internal history as the primary basis for company-specific "
        "decisions and external company cases to generate testable "
        "hypotheses, not guaranteed outcomes. Review the results and "
        "document the decision rationale before expanding. "
        f"{evidence_context}"
    )


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return _deduplicate_strings([
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and not _is_placeholder(item)
    ])


def _validate_model_result(
    result: Any,
    allowed_source_ids: set[str],
    source_provenance: dict[str, dict[str, Any]] | None = None,
    verified_citations: dict[
        tuple[int, str],
        dict[str, Any],
    ] | None = None,
    verification_error: str | None = None,
    fallback_recommendation: str | None = None,
) -> dict[str, Any]:
    """
    Keep only claims with valid structure and independently verified IDs.
    """
    if not isinstance(result, dict):
        raise ProposalAnalysisError(
            "Model returned an invalid analysis object."
        )

    recommendation = result.get("recommendation")

    used_fallback = (
        not isinstance(recommendation, str)
        or not recommendation.strip()
        or _is_placeholder(recommendation)
    )

    if used_fallback:
        recommendation = (
            fallback_recommendation
            or "Insufficient evidence is available to make a reliable "
            "recommendation. Validate the proposal with a controlled "
            "experiment before committing to a wider rollout."
        )

    raw_claims = result.get("claims", [])

    if not isinstance(raw_claims, list):
        raise ProposalAnalysisError(
            "Model returned an invalid claims list."
        )

    source_provenance = source_provenance or {}
    verified_citations = verified_citations or {}

    limitations = _clean_text_list(
        result.get("limitations", [])
    )
    risks = _clean_text_list(
        result.get("risks", [])
    )

    validated_claims = []
    discarded_citation_count = 0
    unsupported_claim_count = 0
    normalized_claim_count = 0

    for claim_index, claim in enumerate(raw_claims):
        if not isinstance(claim, dict):
            limitations.append(
                "An invalid claim object returned by the model was discarded."
            )
            continue

        statement = claim.get("statement")
        raw_claim_type = claim.get("type")
        source_ids = claim.get("source_ids", [])

        if not isinstance(statement, str) or not statement.strip():
            limitations.append(
                "A claim with an empty or invalid statement was discarded."
            )
            continue

        claim_type, was_normalized = _normalize_claim_type(
            raw_claim_type
        )

        if was_normalized or claim.get("_type_normalized") is True:
            normalized_claim_count += 1

        if not isinstance(source_ids, list):
            source_ids = []

        requested_ids = {
            source_id
            for source_id in source_ids
            if isinstance(source_id, str)
        }

        invalid_ids = requested_ids - allowed_source_ids

        if invalid_ids:
            limitations.append(
                "A claim attempted to reference unavailable source IDs. "
                "Those references were discarded."
            )

        candidates = requested_ids.intersection(
            allowed_source_ids
        )

        valid_ids = []

        for source_id in candidates:
            verification = verified_citations.get(
                (claim_index, source_id)
            )

            if (
                isinstance(verification, dict)
                and verification.get("source_id") == source_id
                and isinstance(
                    verification.get("supporting_quote"),
                    str,
                )
                and verification["supporting_quote"].strip()
            ):
                valid_ids.append(source_id)
            else:
                discarded_citation_count += 1

        valid_ids.sort()

        provenance = [
            {
                "source_id": source_id,
                **source_provenance.get(source_id, {}),
            }
            for source_id in valid_ids
        ]

        scopes = {
            source_provenance.get(source_id, {}).get(
                "evidence_scope",
                "unknown",
            )
            for source_id in valid_ids
        }

        if not valid_ids:
            evidence_scope = "unsupported"
            evidence_status = "unsupported"
            verification_status = "unverified"
            unsupported_claim_count += 1
        else:
            evidence_status = "cited_context"
            verification_status = "verified"

            if scopes == {"internal"}:
                evidence_scope = "internal"
            elif scopes == {"external_public"}:
                evidence_scope = "external"
            elif (
                "internal" in scopes
                and "external_public" in scopes
            ):
                evidence_scope = "mixed"
            else:
                evidence_scope = "unknown"

        validated_claims.append({
            "statement": statement.strip(),
            "type": claim_type,
            "source_ids": valid_ids,
            "evidence_status": evidence_status,
            "verification_status": verification_status,
            "evidence_scope": evidence_scope,
            "source_provenance": provenance,
        })

    if normalized_claim_count:
        limitations.append(
            f"{normalized_claim_count} claim(s) returned a missing or "
            "non-standard claim type. They were conservatively retained "
            "as hypotheses or normalized to the supported claim types. "
            "Their citations still had to pass independent verification."
        )

    if used_fallback:
        limitations.append(
            "The model returned an empty or generic recommendation. "
            "A conservative proposal-aware validation recommendation "
            "was used instead."
        )

    if discarded_citation_count:
        limitations.append(
            f"{discarded_citation_count} candidate citation(s) were "
            "rejected because independent verification did not confirm "
            "support for the complete claim."
        )

    if unsupported_claim_count:
        limitations.append(
            f"{unsupported_claim_count} claim(s) have no citations that "
            "passed independent evidence verification. They remain "
            "unsupported and are not treated as source-backed facts."
        )

    if verification_error:
        limitations.append(
            "Independent evidence verification was incomplete or failed: "
            f"{verification_error}. Citations without successful "
            "verification were not accepted."
        )

    return {
        "recommendation": recommendation.strip(),
        "risks": risks,
        "limitations": _deduplicate_strings(limitations),
        "claims": validated_claims,
    }


def _format_graph_context(graph_context: Any) -> str:
    """
    Format graph context as supplementary reasoning context.

    Graph context is not document evidence and must not be cited
    as support for factual claims.
    """
    if graph_context is None:
        return ""

    if not isinstance(graph_context, dict):
        raise ValueError("Graph context must be a dictionary.")

    events = graph_context.get("events", [])

    if not isinstance(events, list):
        raise ValueError("Graph context events must be a list.")

    safe_events = []

    for event in events[:30]:
        if not isinstance(event, dict):
            continue

        relationships = event.get("relationships", [])
        if not isinstance(relationships, list):
            relationships = []

        safe_events.append({
            "event_id": event.get("event_id"),
            "product_name": event.get("product_name"),
            "event_type": event.get("event_type"),
            "title": event.get("title"),
            "description": event.get("description"),
            "event_date": event.get("event_date"),
            "stated_reason": event.get("stated_reason"),
            "reported_outcome": event.get("reported_outcome"),
            "evidence_classification": event.get(
                "evidence_classification"
            ),
            "relationships": relationships[:20],
        })

    if not safe_events:
        return ""

    formatted = {
        "company_id": graph_context.get("company_id"),
        "event_count": graph_context.get(
            "event_count",
            len(safe_events),
        ),
        "events": safe_events,
        "interpretation_warning": graph_context.get(
            "interpretation_warning",
            "Chronology and stored relationships do not establish causation.",
        ),
    }

    return json.dumps(
        formatted,
        ensure_ascii=False,
        default=str,
    )



def _format_customer_feedback(items: list[dict[str, Any]]) -> str:
    """Group feedback by relevance while keeping it separate from documentary evidence."""
    direct = []
    related = []
    other = []

    direct_terms = {
        "search",
        "searching",
        "searches",
    }

    related_terms = {
        "performance",
        "slow",
        "slower",
        "speed",
        "usability",
        "usable",
        "reliability",
        "reliable",
        "navigation",
        "navigate",
        "interface",
        "design",
        "crash",
        "crashes",
        "responsive",
        "responsiveness",
    }

    def format_item(index: int, item: dict[str, Any]) -> str:
        topics = item.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        source_url = str(item.get("source_url") or "Not available")

        return (
            f"FEEDBACK ITEM {index}\n"
            f"FEEDBACK_ID: {item.get('feedback_id') or 'Not available'}\n"
            f"PRODUCT: {item.get('product_name') or 'Not specified'}\n"
            f"SENTIMENT: {item.get('sentiment') or 'unknown'}\n"
            f"FEEDBACK_TYPE: {item.get('feedback_type') or 'other'}\n"
            f"TOPICS: {', '.join(str(topic) for topic in topics)}\n"
            f"RATING: {item.get('rating') if item.get('rating') is not None else 'Not provided'}\n"
            f"FEEDBACK_DATE: {item.get('feedback_date') or 'Not available'}\n"
            f"SOURCE_URL: {source_url}\n"
            f"FEEDBACK_TEXT:\n{item.get('feedback_text', '')}"
        )

    for index, item in enumerate(items, start=1):
        feedback_text = str(item.get("feedback_text") or "").lower()
        words = set(re.findall(r"[a-z]+", feedback_text))

        topics = item.get("topics", [])
        if isinstance(topics, list):
            topic_words = set(
                word
                for topic in topics
                for word in re.findall(r"[a-z]+", str(topic).lower())
            )
            words.update(topic_words)

        formatted_item = format_item(index, item)

        if words.intersection(direct_terms):
            direct.append(formatted_item)
        elif words.intersection(related_terms):
            related.append(formatted_item)
        else:
            other.append(formatted_item)

    sections = [
        (
            "DIRECTLY RELEVANT CUSTOMER FEEDBACK "
            f"({len(direct)} item(s))",
            direct,
        ),
        (
            "RELATED USABILITY / PERFORMANCE FEEDBACK "
            f"({len(related)} item(s))",
            related,
        ),
        (
            "OTHER CUSTOMER FEEDBACK "
            f"({len(other)} item(s))",
            other,
        ),
    ]

    blocks = [
        "FEEDBACK RELEVANCE GROUPING:\n"
        "- Groups are based on simple keyword matching, not semantic verification.\n"
        "- A group assignment does not establish a verified customer trend.\n"
        "- Preserve the original feedback wording and individual ratings.\n"
        "- Sentiment and feedback-type labels are heuristic and may be inaccurate.\n"
        "- URLs using example.com appear sample-like; their provenance is not verified.\n"
        "- Feedback is a separate customer signal, not documentary evidence."
    ]

    for heading, entries in sections:
        if entries:
            blocks.append(
                heading + "\n\n" + "\n\n".join(entries)
            )

    return "\n\n".join(blocks)


def analyze_proposal_with_evidence(
    title: str,
    description: str,
    evidence_chunks: list[dict[str, Any]],
    external_evidence_chunks: list[dict[str, Any]] | None = None,
    graph_context: dict[str, Any] | None = None,
    customer_feedback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Analyze a proposal using internal and eligible external evidence.

    Graph context is supplementary reasoning context only. It is never
    included in the source pool used for factual claim verification.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Proposal title cannot be empty.")

    if not isinstance(description, str) or not description.strip():
        raise ValueError("Proposal description cannot be empty.")

    if not isinstance(evidence_chunks, list):
        raise ValueError("Internal evidence chunks must be a list.")

    if external_evidence_chunks is None:
        external_evidence_chunks = []

    if not isinstance(external_evidence_chunks, list):
        raise ValueError("External evidence chunks must be a list.")

    if customer_feedback is None:
        customer_feedback = []

    if not isinstance(customer_feedback, list):
        raise ValueError("Customer feedback must be a list.")

    customer_feedback = [
        item
        for item in customer_feedback
        if isinstance(item, dict)
        and isinstance(item.get("feedback_text"), str)
        and item["feedback_text"].strip()
    ][:30]

    internal_chunks = _usable_chunks(evidence_chunks)
    supplied_external = _usable_chunks(
        external_evidence_chunks
    )

    external_chunks = [
        item
        for item in supplied_external
        if item.get("evidence_scope") == "external_public"
        and item.get("permission_status") == "public"
        and item.get("source_company_id")
        and item.get("source_company_id")
        != item.get("proposing_company_id")
    ]

    rejected_external_count = (
        len(supplied_external) - len(external_chunks)
    )

    usable_evidence = (
        [(item, "internal") for item in internal_chunks]
        + [
            (item, "external_public")
            for item in external_chunks
        ]
    )

    source_provenance: dict[str, dict[str, Any]] = {}
    source_text_by_id: dict[str, list[str]] = {}
    source_context_by_id: dict[str, dict[str, Any]] = {}

    for item, scope in usable_evidence:
        source_id = item["source_id"]

        provenance = {
            "evidence_scope": scope,
            "source_company_id": item.get("source_company_id"),
            "source_company_name": item.get("source_company_name"),
            "source_company_industry": item.get(
                "source_company_industry"
            ),
            "source_title": item.get("source_title"),
            "source_url": item.get("source_url"),
        }

        if source_id not in source_provenance:
            source_provenance[source_id] = provenance
        elif (
            source_provenance[source_id]["evidence_scope"] != scope
        ):
            raise ProposalAnalysisError(
                f"Source {source_id} was supplied as both internal and "
                "external evidence. Resolve the provenance conflict first."
            )

        passages = source_text_by_id.setdefault(
            source_id,
            [],
        )

        if item["chunk_text"] not in passages:
            passages.append(item["chunk_text"])

        source_context_by_id[source_id] = {
            "source_company_name": item.get(
                "source_company_name"
            ),
        }

    if not usable_evidence and not customer_feedback:
        limitations = [
            "No relevant internal or eligible external evidence chunks "
            "were retrieved.",
            "No model-generated recommendation was attempted.",
        ]

        if rejected_external_count:
            limitations.append(
                f"{rejected_external_count} external evidence chunk(s) "
                "were rejected because public permission or external "
                "provenance could not be established."
            )

        return {
            "status": "completed",
            "recommendation": (
                "Insufficient historical evidence is available to make "
                "an evidence-grounded recommendation. Collect relevant "
                "company documents, decisions or public case studies "
                "before proceeding."
            ),
            "risks": [],
            "limitations": limitations,
            "claims": [],
            "referenced_source_ids": [],
            "evidence_sources": [],
        }

    allowed_source_ids = set(source_text_by_id)

    evidence_blocks = []

    for scope, chunks in (
        ("INTERNAL", internal_chunks),
        ("EXTERNAL_PUBLIC", external_chunks),
    ):
        if not chunks:
            continue

        evidence_blocks.append(
            f"===== {scope} EVIDENCE ====="
        )

        for index, item in enumerate(chunks, start=1):
            evidence_blocks.append(
                f"EVIDENCE {index}\n"
                f"EVIDENCE_SCOPE: {scope}\n"
                f"SOURCE_ID: {item['source_id']}\n"
                f"COMPANY: "
                f"{item.get('source_company_name') or 'Not available'}\n"
                f"SOURCE_TITLE: "
                f"{item.get('source_title') or 'Not available'}\n"
                f"SOURCE_URL: "
                f"{item.get('source_url') or 'Not available'}\n"
                f"CONTENT:\n{item['chunk_text']}"
            )

    customer_feedback_message = ""

    if customer_feedback:
        formatted_feedback = _format_customer_feedback(
            customer_feedback
        )

        customer_feedback_message = (
            "\n\nCUSTOMER FEEDBACK "
            "(SEPARATE NON-DOCUMENT SIGNALS; NOT CITABLE EVIDENCE):\n"
            f"{formatted_feedback}\n\n"
            "CUSTOMER FEEDBACK RULES:\n"
            "- Feedback is a signal of customer experiences, needs, "
            "complaints, preferences or requests.\n"
            "- Feedback is NOT documentary proof of product events, "
            "business outcomes, causation or experiment results.\n"
            "- Sentiment and topic labels are heuristic classifications, "
            "not independently verified facts.\n"
            "- Do not invent customer counts, percentages or trends.\n"
            "- Do not cite feedback IDs as document source IDs.\n"
            "- Use feedback to identify customer needs, risks and "
            "validation opportunities.\n"
            "- Distinguish individual feedback examples from broader "
            "patterns.\n"
        )

    formatted_graph_context = _format_graph_context(
        graph_context
    )

    graph_context_message = ""

    if formatted_graph_context:
        graph_context_message = (
            "\n\nSUPPLEMENTARY KNOWLEDGE GRAPH CONTEXT "
            "(NOT DOCUMENT EVIDENCE):\n"
            f"{formatted_graph_context}\n\n"
            "GRAPH CONTEXT RULES:\n"
            "- This graph is supplementary historical context only.\n"
            "- It is NOT document evidence and has no citable source passages.\n"
            "- Never cite graph event IDs as source IDs.\n"
            "- Do not create factual claims from graph context alone.\n"
            "- Use it only to identify possible patterns, questions, risks, "
            "and hypotheses.\n"
            "- Chronology and stored relationships do not establish causation.\n"
        )

    user_message = (
        "Analyze this proposal using the supplied historical evidence.\n"
        "Create atomic claims: one event and one main factual assertion "
        "per claim. If a date and a stated reason are supported by "
        "different passages, create separate claims. Attribute every "
        "external event to the company that performed it. Use CONTENT "
        "passages only. Preserve all important qualifiers, numbers and "
        "dates. Do not return generic placeholders.\n\n"
        "The recommendation must address the actual proposal. Distinguish "
        "documented facts from hypotheses. Do not treat another company's "
        "strategy as proof that the same strategy will work for the "
        "proposing company. If evidence is insufficient, recommend a "
        "specific validation step rather than inventing a conclusion.\n\n"
        f"PROPOSAL TITLE:\n{title.strip()}\n\n"
        f"PROPOSAL DESCRIPTION:\n{description.strip()}\n\n"
        "HISTORICAL EVIDENCE:\n"
        + "\n\n".join(evidence_blocks)
        + customer_feedback_message
        + graph_context_message
    )

    parsed = _call_ollama_json(
        PROPOSAL_ANALYSIS_PROMPT,
        user_message,
        timeout=PROPOSAL_ANALYSIS_TIMEOUT,
        response_schema=PROPOSAL_ANALYSIS_SCHEMA,
    )

    if not isinstance(parsed.get("claims"), list):
        logger.warning(
            "Proposal model returned an invalid claims field "
            "(type=%s). Discarding all model-generated claims.",
            type(parsed.get("claims")).__name__,
        )

        parsed["claims"] = []

        existing_limitations = parsed.get("limitations")
        if not isinstance(existing_limitations, list):
            existing_limitations = []

        existing_limitations.append(
            "The model did not return claims in the required list format. "
            "All model-generated claims were discarded; no claims were "
            "accepted or verified."
        )
        parsed["limitations"] = existing_limitations

    normalized_claims, normalized_type_count = (
        _normalize_claim_types(parsed["claims"])
    )

    parsed["claims"] = normalized_claims

    if normalized_type_count:
        logger.warning(
            "Normalized %d non-standard or missing claim type(s).",
            normalized_type_count,
        )

    enriched_claims, assignment_error = _assign_claim_sources(
        parsed["claims"],
        [
            item
            for item, _scope in usable_evidence
        ],
        allowed_source_ids,
    )

    parsed["claims"] = enriched_claims

    verification_claims = _prepare_verification_claims(
        parsed["claims"],
        allowed_source_ids,
    )

    verified_citations = {}
    verification_error = None

    if verification_claims:
        verified_citations, verification_error = (
            verify_claim_citations(
                verification_claims,
                source_text_by_id,
                source_context_by_id,
            )
        )

    logger.info(
        "Proposal citation verification completed: "
        "%d claim(s), %d verified claim/source pair(s), "
        "verification_error=%s",
        len(verification_claims),
        len(verified_citations),
        verification_error,
    )

    fallback = _fallback_recommendation(
        title,
        description,
        len(internal_chunks),
        len(external_chunks),
    )

    validated = _validate_model_result(
        parsed,
        allowed_source_ids,
        source_provenance,
        verified_citations,
        verification_error,
        fallback,
    )

    validated["status"] = "completed"

    if formatted_graph_context:
        validated["limitations"].append(
            "Historical knowledge graph context was supplied as supplementary "
            "reasoning context. It is not document-backed evidence, cannot "
            "independently support factual claims or citations, and its stored "
            "relationships do not establish causation."
        )

    if assignment_error:
        validated["limitations"].append(
            assignment_error
        )

    validated["referenced_source_ids"] = sorted({
        source_id
        for claim in validated["claims"]
        for source_id in claim["source_ids"]
    })

    validated["evidence_sources"] = [
        {
            "source_id": item["source_id"],
            **source_provenance[item["source_id"]],
            "similarity": item.get("similarity"),
        }
        for item, _scope in usable_evidence
    ]

    if rejected_external_count:
        validated["limitations"].append(
            f"{rejected_external_count} external evidence chunk(s) "
            "were rejected because public permission or external "
            "provenance could not be established."
        )

    validated["limitations"].extend([
        "A claim marked verified has at least one citation whose supporting "
        "quotation passed checks against its original source passage. This "
        "verifies textual support, not the truthfulness or completeness of "
        "the publisher's underlying report.",
        "Claims marked unsupported have no citation that passed independent "
        "verification and must not be presented as documented facts.",
        "Citations are checked against their specific original source "
        "passages. Supporting quotations must exist in the original "
        "passage, and numeric details and material qualifiers must "
        "be supported.",
        "Supplementary source selection proposes candidate citations "
        "only. Independent verification determines which citations "
        "are accepted.",
        "Claims without a validated citation remain unsupported.",
        "Similarity scores rank retrieved text and do not establish "
        "truth, causation or factual confidence.",
        "Recommendations and risks are model-generated analysis, not "
        "independently verified historical facts.",
    ])

    if external_chunks:
        validated["limitations"].append(
            "External public case studies describe other companies. "
            "Their outcomes do not establish what will happen at the "
            "proposing company."
        )

    if customer_feedback:
        validated["limitations"].append(
            "Customer feedback was supplied as a separate non-document "
            "signal. It cannot independently support document citations, "
            "prove product outcomes or establish causation."
        )
        validated["limitations"].append(
            "Feedback sentiment and topic labels are produced by a "
            "rule-based heuristic classifier and may be inaccurate."
        )

    if not usable_evidence and customer_feedback:
        validated["limitations"].append(
            "No relevant internal or eligible external documentary "
            "evidence was available. Claims therefore remain unsupported "
            "unless independently verified document citations exist."
        )

    validated["limitations"] = _deduplicate_strings(
        validated["limitations"]
    )


    return validated