import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.embeddings import (
    EmbeddingError,
    search_external_public_chunks,
    search_similar_chunks,
)
from app.intelligence.claim_verification import verify_claim_citations
from app.intelligence.knowledge_retrieval import append_relevant_knowledge_item_passages
from app.models import Company, SourceDocument


MAX_CANDIDATE_CLAIMS = 12
MAX_CANDIDATE_SENTENCE_CHARS = 1200


MONTH_NUMBERS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _requested_publication_period(query: str) -> tuple[int, int] | None:
    """Return an explicitly requested month/year from the question."""
    month_pattern = "|".join(MONTH_NUMBERS)
    match = re.search(
        rf"\b({month_pattern})\s+((?:19|20)\d{{2}})\b",
        query,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return (int(match.group(2)), MONTH_NUMBERS[match.group(1).casefold()])


def _publication_date_matches(
    publication_date: Any,
    requested_period: tuple[int, int],
) -> bool:
    """Match a source publication date to an explicitly requested month/year."""
    if publication_date is None:
        return False

    if isinstance(publication_date, str):
        try:
            publication_date = datetime.fromisoformat(
                publication_date.replace("Z", "+00:00")
            )
        except ValueError:
            return False

    if not isinstance(publication_date, datetime):
        return False

    return (publication_date.year, publication_date.month) == requested_period


def _filter_evidence_by_publication_period(
    evidence: list[dict[str, Any]],
    requested_period: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    """When the query names a month/year, retain only sources dated in it."""
    if requested_period is None:
        return evidence

    return [
        item
        for item in evidence
        if _publication_date_matches(
            item.get("publication_date"), requested_period
        )
    ]


STOP_WORDS = {
    "what", "which", "when", "where", "who", "why", "how",
    "does", "do", "did", "is", "are", "was", "were", "has",
    "the", "a", "an", "and", "or", "but", "to", "of",
    "in", "on", "at", "for", "from", "with", "by",
    "it", "its", "this", "that", "these", "those",
    "can", "could", "would", "should", "will",
    "company", "companies",
}

QUERY_EXPANSIONS = {
    "streaming": {"stream", "watch", "instantly", "online"},
    "stream": {"streaming", "watch", "instantly", "online"},

    "features": {
        "feature", "device", "devices", "app", "apps",
        "phone", "phones", "mobile", "tablet", "tablets",
        "computer", "computers", "television", "tv",
        "console", "download", "downloads", "profile",
    },
    "feature": {
        "features", "device", "devices", "app", "apps",
        "phone", "phones", "mobile", "tablet", "tablets",
        "computer", "computers", "television", "tv",
        "console", "download", "downloads", "profile",
    },

    # Historical event terminology.
    "historical": {
        "announced", "introduced", "launched", "expanded",
        "shipped", "discontinued", "released", "rolled",
        "rollout", "closed", "ended",
    },
    "changes": {
        "change", "announced", "introduced", "launched",
        "expanded", "shipped", "discontinued", "released",
        "rollout", "added", "removed", "ended",
    },
    "introduced": {
        "announced", "launched", "released", "expanded",
        "shipped", "discontinued",
    },
    "major": {
        "announced", "introduced", "launched", "expanded",
        "shipped", "discontinued",
    },
    "product": {
        "products", "service", "services", "feature", "features",
        "subscription", "subscriptions", "plan", "plans",
        "streaming", "dvd", "ads",
    },
}

# Common page labels and navigation fragments that should not become
# standalone factual claims.
NOISE_PATTERNS = (
    r"^help center$",
    r"^help home$",
    r"^back to help home$",
    r"^frequently asked questions$",
    r"^trending now$",
    r"^more reasons to join$",
    r"^email address$",
    r"^join netflix$",
    r"^sign in$",
    r"^computers$",
    r"^mobile phones and tablets$",
    r"^tvs and tv streaming devices$",
    r"^cable boxes$",
    r"^android phone or tablet$",
    r"^iphone or ipad$",
    r"^amazon fire tablet$",
    r"^windows tablet$",
)

LIST_HEADING_PREFIXES = (
    "netflix supported devices",
    "netflix india",
    "watch everywhere",
    "enjoy on your tv",
    "watch on smart tvs",
    "amazon fire tv",
    "apple tv",
    "chromecast",
    "hisense",
    "panasonic",
    "philips",
    "roku",
    "samsung",
    "sharp",
    "sony",
    "tcl",
    "vestel",
    "vizio",
    "toshiba",
)


class RAGError(Exception):
    """Raised when evidence-grounded question answering fails."""


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[a-zA-Z0-9]+", text)
        if token.casefold() not in STOP_WORDS
    }


def _query_vocabulary(
    query: str,
    company_name: str,
) -> set[str]:
    terms = _tokens(query)
    terms -= _tokens(company_name)

    expanded = set(terms)

    for term in terms:
        expanded.update(QUERY_EXPANSIONS.get(term, set()))

    return expanded


def _is_noise_sentence(sentence: str) -> bool:
    normalized = re.sub(r"\s+", " ", sentence).strip()
    folded = normalized.casefold()

    if not normalized:
        return True

    if any(
        re.fullmatch(pattern, folded)
        for pattern in NOISE_PATTERNS
    ):
        return True

    # Product-page widgets often survive text cleaning. They are not
    # evidence for product launch, change, or outcome questions.
    if re.search(
        r"\b(?:layer popup|see more content|solutions?\s*&\s*tips|"
        r"close download)\b",
        folded,
    ):
        return True

    if re.search(
        r"\ball features,? specifications,? and prices? are subject to change\b",
        folded,
    ):
        return True

    if re.search(
        r"\b(?:please accept the .*privacy policy|enquiry has been "
        r"successfully submitted|get stock alert|enter your email or "
        r"phone number|double check your email|notify you when inventory "
        r"is added|service only available with .*series|images shown .*"
        r"representational purpose|availability of colors may vary|"
        r"model availability may vary|account login may be required)\b",
        folded,
    ):
        return True

    if folded.startswith("everything you need to know about this upgrade"):
        return True

    if re.search(
        r"\b(?:terms and conditions|privacy policy|checkbox is required|"
        r"clicking submit|verification expired|authenticity policy|"
        r"anti-fraud technology|reviews are managed by|please contact "
        r"manager|how to fix if|please double check|no liability for reliance)\b",
        folded,
    ):
        return True

    if re.search(
        r"\b(?:availability|colors?|colours?|sizes?|models?|watch bands?) "
        r"may vary\b",
        folded,
    ):
        return True

    # Reject page-title fragments followed by navigation or content.
    if folded.startswith("netflix supported devices |"):
        return True

    if folded.startswith("netflix india â€“"):
        return True

    has_event_verb = bool(
        re.search(
            r"\b(?:announced|introduced|launched|expanded|"
            r"shipped|discontinued|released|rolled out|"
            r"ended|removed|added|closed)\b",
            folded,
        )
    )
    has_outcome_verb = bool(
        re.search(
            r"\b(?:increased|decreased|improved|reduced|rose|fell|grew|"
            r"declined|dropped|reached|achieved|remained|measured|"
            r"resulted|yielded)\b",
            folded,
        )
    )

    # Reject fragments that are primarily a device/vendor list.
    # Completed event and measured-outcome statements are exempt even when
    # they do not use a launch verb.
    if (
        not has_event_verb
        and not has_outcome_verb
        and len(normalized) > 100
        and not re.search(
            r"\b(can|is|are|offers|include|watch|stream)\b",
            folded,
        )
        and len(_tokens(normalized)) > 12
    ):
        return True

    # A sentence containing navigation labels is often a scraped page
    # fragment rather than a coherent factual statement.
    navigation_terms = {
        "email", "trending", "signin", "join", "homepage",
    }

    if len(navigation_terms.intersection(_tokens(normalized))) >= 2:
        return True

    # Reject heading-like fragments with no sentence-ending punctuation.
    if not re.search(r"[.!?][\"')\]]?$", normalized):
        return True

    return False


def _split_sentences(text: str) -> list[str]:
    """
    Extract complete factual sentence candidates from flattened
    webpage text. Original factual wording is preserved.
    """

    if not isinstance(text, str) or not text.strip():
        return []

    normalized = re.sub(r"\s+", " ", text).strip()

    # Remove common page-navigation text before sentence splitting.
    navigation_patterns = [
        r"Help Center",
        r"Join Netflix",
        r"Sign In",
        r"Back to Help Home",
        r"Frequently Asked Questions",
        r"Email address",
        r"Trending Now",
        r"More reasons to join",
    ]

    for pattern in navigation_patterns:
        normalized = re.sub(
            pattern,
            " ",
            normalized,
            flags=re.IGNORECASE,
        )

    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Separate known headings from the factual text that follows.
    heading_patterns = [
        r"Mobile phones and tablets",
        r"TVs and TV streaming devices",
        r"Cable boxes",
        r"Computers",
        r"Watch everywhere",
        r"Watch on smart TVs",
        r"Enjoy on your TV",
        r"Frequently Asked Questions",
    ]

    for heading in heading_patterns:
        normalized = re.sub(
            rf"\b{re.escape(heading)}\b\s+(?=[A-Z])",
            "",
            normalized,
            flags=re.IGNORECASE,
        )

    parts = re.split(r"(?<=[.!?])\s+", normalized)

    results = []

    for part in parts:
        sentence = part.strip()

        if not 35 <= len(sentence) <= MAX_CANDIDATE_SENTENCE_CHARS:
            continue

        if _is_noise_sentence(sentence):
            continue

        folded = sentence.casefold()

        # Generic navigation instructions are not useful product facts.
        if any(
            phrase in folded
            for phrase in (
                "use the links below",
                "search for your device",
                "learn how to get netflix",
                "back to help",
                "sign in",
                "join netflix",
            )
        ):
            continue

        results.append(sentence)

    return results



QUERY_INTENT_TERMS = {
    "announce", "announced", "announcement", "change", "changes",
    "changed", "introduce", "introduced", "launch", "launched",
    "release", "released", "update", "updated", "expand", "expanded",
    "history", "historical", "price", "pricing", "cost", "feature",
    "features", "current", "currently", "today", "when", "what",
    "date", "dates", "day", "days", "year", "years", "month", "months",
    "reason", "reasons", "purpose", "purposes", "motivation", "motivations",
    "outcome", "outcomes", "impact", "impacts", "effect", "effects",
    "stated", "reported", "documented", "source", "sources", "describe",
    "described", "describes", "variant", "variants", "category", "categories",
    "happen", "happened", "event", "events", "decision", "decisions", "experiment",
    "add", "adds", "added", "adding", "measure", "measured", "measuring",
    "experiments", "result", "results", "outcome", "outcomes",
    "product", "products", "company", "companies", "report",
    "reported", "reports",
    "about", "public", "stored", "collected", "available", "did", "does", "do", "using", "which", "who",
    "where", "why", "how", "is", "are", "was", "were",
    "exact", "calendar", "day", "timing", "geography", "documented",
}

EVENT_TERMS = {
    "announce", "announced", "announcement", "change", "changes",
    "changed", "introduce", "introduced", "launch", "launched",
    "release", "released", "update", "updated", "expand", "expanded",
    "rollout", "rolled", "added", "removed", "discontinued", "ended",
    "price", "pricing", "increased", "increase", "decreased", "decrease",
}


def _query_focus_terms(query: str, company_name: str) -> set[str]:
    """Return product/topic terms, excluding intent words and date filters."""
    terms = _tokens(query) - _tokens(company_name)
    terms -= QUERY_INTENT_TERMS
    terms -= set(MONTH_NUMBERS)
    terms = {
        term for term in terms
        if not re.fullmatch(r"(?:19|20)\d{2}", term)
    }
    return terms


def _query_focus_phrase(query: str, company_name: str) -> str:
    """Preserve the order of product/topic words for exact phrase checks."""
    company_terms = _tokens(company_name)
    kept = []
    for term in re.findall(r"[a-zA-Z0-9]+", query.casefold()):
        if term in STOP_WORDS or term in QUERY_INTENT_TERMS:
            continue
        if term in MONTH_NUMBERS or re.fullmatch(r"(?:19|20)\d{2}", term):
            continue
        if term in company_terms:
            continue
        kept.append(term)
    return " ".join(kept)


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"\b"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _classify_sentence_relevance(
    sentence: str,
    source_title: str,
    sentence_terms: set[str],
    focus_terms: set[str],
    focus_phrase: str,
) -> tuple[str | None, int]:
    """Classify a sentence using both its wording and its source context."""
    if not focus_terms:
        # A broad factual question has no product-specific anchor. Permit
        # retrieved passages to contribute candidates; citation verification
        # and the explicit requested-aspect coverage check remain in force.
        return ("direct_match", 1)

    overlap = sentence_terms.intersection(focus_terms)
    if not overlap:
        return (None, 0)

    title = (source_title or "").casefold()
    sentence_has_phrase = _contains_phrase(sentence, focus_phrase)
    title_has_phrase = _contains_phrase(title, focus_phrase)

    # Do not mistake generic plan-wide benefits for a Premium Family change.
    if re.search(r"\b(?:every|all)\s+premium\s+plans?\b", sentence, re.I):
        if not sentence_has_phrase and not title_has_phrase:
            return ("contextual_only", len(overlap))

    # A Kids or pricing article is a related/later development even if its
    # body mentions Premium Family. It is not part of the original upgrade.
    is_later_topic = any(term in title for term in ("kids", "price", "pricing"))
    if is_later_topic and (sentence_has_phrase or overlap):
        return ("related_development", len(overlap) * 3)

    # The source title can establish the product context for sub-feature
    # sentences such as Family Mix and Family Hub that omit the full plan name.
    if sentence_has_phrase or title_has_phrase:
        return ("direct_match", len(overlap) * 5)

    specific_terms = {
        term for term in focus_terms
        if term not in {"premium", "product", "plan", "plans", "service"}
    }
    if specific_terms.intersection(sentence_terms):
        return ("related_development", len(overlap) * 3)

    return ("contextual_only", len(overlap))

def _extract_candidate_claims(
    evidence: list[dict[str, Any]],
    query: str,
    company_name: str,
    max_claims: int = MAX_CANDIDATE_CLAIMS,
) -> list[dict[str, Any]]:
    """Extract and rank factual sentences by product and query relevance."""

    # Intent words (launch, reason, date, etc.) can rank tangential passages
    # highly without making them relevant to the requested product or topic.
    vocabulary = _query_vocabulary(query, company_name) - QUERY_INTENT_TERMS
    focus_terms = _query_focus_terms(query, company_name)
    focus_phrase = _query_focus_phrase(query, company_name)
    focus_vocabulary = focus_terms.intersection(vocabulary)
    query_requests_events = bool(
        _tokens(query).intersection(EVENT_TERMS)
    )

    candidates = []
    seen = set()

    for evidence_index, item in enumerate(evidence):
        source_id = item.get("source_id")
        passage = item.get("chunk_text")

        if not source_id or not isinstance(passage, str):
            continue

        for sentence_index, sentence in enumerate(_split_sentences(passage)):
            normalized = sentence.casefold()
            dedupe_key = (source_id, normalized)

            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            sentence_terms = _tokens(sentence)
            overlap = vocabulary.intersection(sentence_terms)
            focus_overlap = focus_vocabulary.intersection(sentence_terms)
            relevance_category, focus_score = _classify_sentence_relevance(
                sentence=sentence,
                source_title=item.get("source_title", ""),
                sentence_terms=sentence_terms,
                focus_terms=focus_terms,
                focus_phrase=focus_phrase,
            )
            source_title_has_focus = bool(
                _tokens(item.get("source_title", "")).intersection(focus_terms)
            )

            if (
                query_requests_events
                and sentence_terms.intersection(EVENT_TERMS)
                and relevance_category in {None, "contextual_only"}
                and (not focus_vocabulary or focus_overlap)
            ):
                # Event questions may not repeat the product's name. Retain
                # an event sentence as a candidate; citation verification
                # still decides whether its exact wording is supportable.
                relevance_category = "direct_match"
                focus_score = max(focus_score, 1)

            sentence_aspects = {
                aspect
                for aspect in _requested_answer_aspects(query)
                if _claim_covers_aspect(sentence, aspect)
            }
            requested_aspects = _requested_answer_aspects(query)
            if requested_aspects and not sentence_aspects:
                # Do not pad a multipart answer with unrelated facts just
                # because a sentence came from a product-specific page.
                continue
            requires_sentence_focus = bool(
                "date" in sentence_aspects
                or (
                    "event" in sentence_aspects
                    and not source_title_has_focus
                )
            )
            if sentence_aspects and relevance_category in {None, "contextual_only"} and (
                not focus_terms
                or focus_overlap
                or (source_title_has_focus and not requires_sentence_focus)
            ):
                # Do not borrow a date, reason, or outcome from an unrelated
                # product merely because it answers the same kind of question.
                # For product-specific queries, aspect matches must still be
                # tied to the query terms in the sentence or source title.
                relevance_category = "direct_match"
                focus_score = max(focus_score, 1)

            # Ignore generic contextual mentions when the query identifies
            # a multi-term product, such as Premium Family.
            if relevance_category in {None, "contextual_only"}:
                continue
            if (
                not focus_overlap
                and not focus_score
                and not (
                    query_requests_events
                    and sentence_terms.intersection(EVENT_TERMS)
                    and not focus_vocabulary
                )
            ):
                continue

            similarity = item.get("similarity", 0.0)
            try:
                similarity = float(similarity or 0.0)
            except (TypeError, ValueError):
                similarity = 0.0

            event_score = 0
            if query_requests_events and sentence_terms.intersection(EVENT_TERMS):
                event_score = 2

            # Relevance ranking is not factual verification. Every selected
            # claim still passes through verify_claim_citations below.
            score = (
                focus_score
                + len(overlap)
                + event_score
                + max(0.0, similarity) * 0.25
            )

            candidates.append({
                "statement": sentence,
                "claim_type": "factual_observation",
                "type": "factual_observation",
                "candidate_source_ids": [source_id],
                "relevance_category": relevance_category,
                "_score": score,
                "_evidence_index": evidence_index,
                "_sentence_index": sentence_index,
            })

    candidates.sort(
        key=lambda item: (
            item["_score"],
            -item["_evidence_index"],
            -item["_sentence_index"],
        ),
        reverse=True,
    )

    selected = candidates[:max_claims]

    for item in selected:
        item.pop("_score", None)
        item.pop("_evidence_index", None)
        item.pop("_sentence_index", None)

    return selected


def _prepare_internal_evidence(
    db: Session,
    company: Company,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prepared = []

    for item in results:
        source = db.get(SourceDocument, item["source_id"])

        if source is None or source.company_id != company.id:
            continue

        if source.permission_status not in {
            "public",
            "authorized_internal",
        }:
            continue

        if not item.get("chunk_text"):
            continue

        prepared.append({
            "source_id": source.id,
            "source_title": source.title,
            "source_url": source.original_url or source.url,
            "source_company_id": company.id,
            "source_company_name": company.name,
            "chunk_index": item.get("chunk_index"),
            "chunk_text": item.get("chunk_text"),
            "similarity": item.get("similarity"),
            "publication_date": source.publication_date,
            "publisher": source.publisher,
            "source_type": source.source_type,
            "evidence_scope": (
                "authorized_internal"
                if source.permission_status == "authorized_internal"
                else "public_company"
            ),
            "permission_status": source.permission_status,
            "evidence_origin": (
                (source.source_metadata or {}).get("evidence_origin")
                if isinstance(source.source_metadata, dict)
                else None
            ),
        })

    return prepared


def _diversify_internal_results(
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Prefer one high-ranking passage per source before repeats."""
    selected = []
    deferred = []
    source_counts: dict[str, int] = {}
    seen_chunks: set[tuple[str, str]] = set()

    for item in results:
        source_id = item.get("source_id")
        normalized_chunk = re.sub(
            r"\W+", " ", (item.get("chunk_text") or "").casefold()
        ).strip()
        chunk_key = (source_id or "", normalized_chunk)
        if not source_id or chunk_key in seen_chunks:
            continue
        seen_chunks.add(chunk_key)
        if source_counts.get(source_id, 0) < 1:
            selected.append(item)
            source_counts[source_id] = 1
            if len(selected) == limit:
                return selected
        else:
            deferred.append(item)

    # Allow a second passage from a source only after every distinct source
    # has had a chance to contribute. This avoids one long page dominating.
    for item in deferred:
        source_id = item["source_id"]
        if source_counts.get(source_id, 0) >= 2:
            continue
        selected.append(item)
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        if len(selected) == limit:
            break
    return selected


def _filter_internal_candidates_by_focus(
    results: list[dict[str, Any]],
    query: str,
    company_name: str,
) -> list[dict[str, Any]]:
    """Discard semantically similar passages with no lexical topic anchor.

    Intent words such as "launch" or "reason" are excluded from the focus
    vocabulary. A product-specific question therefore needs at least one
    product/topic term in the passage or its source title before it can enter
    answer generation.
    """
    focus = _query_focus_terms(query, company_name)
    if not focus:
        product_inventory = bool(
            re.search(r"\bwhat\s+products?\b", query, re.IGNORECASE)
        )
        if not product_inventory:
            return results

        general_source_terms = {
            "company info", "company information", "about us",
            "business area", "business offers", "brand identity",
            "ethics", "investor relations",
        }
        return [
            item
            for item in results
            if not any(
                term in (item.get("source_title") or "").casefold()
                for term in general_source_terms
            )
        ]

    ranked = []
    for index, item in enumerate(results):
        passage_tokens = _tokens(item.get("chunk_text") or "")
        title_tokens = _tokens(item.get("source_title") or "")
        matching_terms = focus.intersection(passage_tokens | title_tokens)
        phrase = _query_focus_phrase(query, company_name)
        phrase_match = _contains_phrase(
            f"{item.get('source_title') or ''} {item.get('chunk_text') or ''}",
            phrase,
        )
        required_matches = 1 if len(focus) == 1 else max(
            2,
            (len(focus) + 1) // 2,
        )
        if len(matching_terms) < required_matches and not phrase_match:
            continue
        relevance = len(matching_terms) / len(focus)
        if phrase_match:
            relevance += 2.0
        try:
            similarity = float(item.get("similarity") or 0.0)
        except (TypeError, ValueError):
            similarity = 0.0

        ranked.append((relevance, similarity, -index, item))

    ranked.sort(key=lambda row: row[:3], reverse=True)
    return [item for _, _, _, item in ranked]


def _prepare_external_evidence(
    results: list[dict[str, Any]],
    target_company_id: str,
) -> list[dict[str, Any]]:
    prepared = []

    for item in results:
        if item.get("evidence_scope") != "external_public":
            continue

        if item.get("permission_status") != "public":
            continue

        if item.get("source_company_id") == target_company_id:
            continue

        if not item.get("source_id") or not item.get("chunk_text"):
            continue

        prepared.append({
            "source_id": item["source_id"],
            "source_title": item.get("source_title"),
            "source_url": item.get("source_url"),
            "source_company_id": item.get("source_company_id"),
            "source_company_name": item.get("source_company_name"),
            "source_company_industry": item.get(
                "source_company_industry"
            ),
            "chunk_index": item.get("chunk_index"),
            "chunk_text": item.get("chunk_text"),
            "similarity": item.get("similarity"),
            "publication_date": item.get("publication_date"),
            "publisher": item.get("publisher"),
            "source_type": item.get("source_type"),
            "evidence_scope": "external_public",
            "permission_status": "public",
        })

    return prepared


def _build_source_maps(
    evidence: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    source_text_by_id: dict[str, list[str]] = {}
    source_context_by_id: dict[str, dict[str, Any]] = {}

    for item in evidence:
        source_id = item["source_id"]
        source_text_by_id.setdefault(source_id, [])

        passage = item["chunk_text"]

        if passage not in source_text_by_id[source_id]:
            source_text_by_id[source_id].append(passage)

        source_context_by_id[source_id] = {
            "source_id": source_id,
            "source_title": item.get("source_title"),
            "source_url": item.get("source_url"),
            "source_company_id": item.get("source_company_id"),
            "source_company_name": item.get("source_company_name"),
            "evidence_scope": item.get("evidence_scope"),
            "permission_status": item.get("permission_status"),
        }

    return source_text_by_id, source_context_by_id


def _verification_service_unavailable(
    verification_error: str | None,
) -> bool:
    if not verification_error:
        return False

    error = verification_error.casefold()

    indicators = (
        "batch failed",
        "could not connect to ollama",
        "verification timed out",
        "request timed out",
        "invalid response",
        "no valid verifications list",
        "invalid response object",
    )

    return any(indicator in error for indicator in indicators)


def _claim_chronology_key(claim: dict[str, Any]) -> tuple:
    """
    Sort verified claims using dates explicitly present in their
    source-supported statements.

    Full dates are preferred. Year-only references are sorted by year.
    Claims without an identifiable year appear last.
    """

    statement = claim.get("statement", "")

    if not isinstance(statement, str):
        return (9999, 13, 32, 1)

    month_names = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    full_date = re.search(
        r"\b(january|february|march|april|may|june|july|"
        r"august|september|october|november|december)"
        r"\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b",
        statement,
        flags=re.IGNORECASE,
    )

    if full_date:
        month = month_names[full_date.group(1).casefold()]
        day = int(full_date.group(2))
        year = int(full_date.group(3))

        return (year, month, day, 0)

    year_match = re.search(
        r"\b((?:19|20)\d{2})\b",
        statement,
    )

    if year_match:
        year = int(year_match.group(1))
        return (year, 13, 32, 0)

    return (9999, 13, 32, 1)


def _build_verified_claims(
    claims: list[dict[str, Any]],
    verification_results: dict,
    evidence_by_id: dict[str, dict[str, Any]],
    verification_unavailable: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verified_claims = []
    unsupported_claims = []

    for claim_index, claim in enumerate(claims):
        verified_citations = []

        for source_id in claim["candidate_source_ids"]:
            verification = verification_results.get(
                (claim_index, source_id)
            )

            if not isinstance(verification, dict):
                continue

            source = evidence_by_id.get(source_id)

            if source is None:
                continue

            quote = verification.get("supporting_quote")

            if not isinstance(quote, str) or not quote.strip():
                continue

            verified_citations.append({
                "source_id": source_id,
                "source_title": source.get("source_title"),
                "source_url": source.get("source_url"),
                "source_company_name": source.get(
                    "source_company_name"
                ),
                "evidence_scope": source.get("evidence_scope"),
                "supporting_quote": quote,
                "verification_method": verification.get(
                    "verification_method"
                ),
                "passage_index": verification.get("passage_index"),
                "verification_status": "textually_supported",
            })

        if verified_citations:
            verified_claims.append({
                "statement": verified_citations[0]["supporting_quote"],
                "claim_type": "factual_observation",
                "candidate_source_ids": claim["candidate_source_ids"],
                "relevance_category": claim.get(
                    "relevance_category", "direct_match"
                ),
                "citations": verified_citations,
                "verification_status": "textually_supported",
            })
        else:
            unsupported_claims.append({
                "statement": claim["statement"],
                "claim_type": claim["claim_type"],
                "candidate_source_ids": claim["candidate_source_ids"],
                "citations": [],
                "verification_status": (
                    "verification_unavailable"
                    if verification_unavailable
                    else "unsupported"
                ),
            })

    return verified_claims, unsupported_claims


def _requested_answer_aspects(query: str) -> set[str]:
    """Identify factual parts explicitly requested by a question."""
    folded = query.casefold()
    aspects = set()
    if re.search(r"\b(when|dates?|days?|timing|years?|months?|how long)\b", folded):
        aspects.add("date")
    if re.search(r"\b(why|reasons?|purposes?|motivations?)\b", folded):
        aspects.add("reason")
    if re.search(r"\b(experiments?|trials?|a/b tests?|tests? conducted)\b", folded):
        aspects.add("experiment")
    if re.search(r"\b(results?|outcomes?|impacts?|effects?)\b", folded):
        aspects.add("outcome")
    if re.search(r"\b(launch|launched|introduc|event|change|decision)\w*\b", folded) or re.search(r"\bwhat product\b", folded):
        aspects.add("event")
    return aspects


def _claim_covers_aspect(statement: str, aspect: str) -> bool:
    folded = statement.casefold()
    if aspect == "date":
        date_matches = list(re.finditer(
            r"\b(?:19|20)\d{2}\b|"
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
            r"[a-z]*\s+\d{1,2}(?:,?\s+(?:19|20)\d{2})?\b|"
            r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
            r"[a-z]*\s+(?:19|20)\d{2}\b",
            folded,
        ))
        event_terms = re.compile(
            r"\b(?:announced|launched|introduced|released|unveiled|"
            r"became available|went on sale|rolled out|discontinued|"
            r"reformulated|redesigned|added|removed|increased|decreased|"
            r"changed)\b"
        )
        for match in date_matches:
            context = folded[
                max(0, match.start() - 100):
                min(len(folded), match.end() + 100)
            ]
            if re.search(r"\b(?:published|publication|posted|copyright)\b", context):
                continue
            if event_terms.search(context):
                return True
        return False
    if aspect == "reason":
        return bool(re.search(r"\b(because|reasons?|purposes?|aimed|designed|intended|in order to|to improve|to help|to simplify|to address)\b", folded))
    if aspect == "experiment":
        return bool(re.search(r"\b(experiment|trial|a/b test|tested|testing)\b", folded))
    if aspect == "outcome":
        reports_absence = bool(
            re.search(
                r"\b(?:no|not|never|without|did not|does not|was not|were not)\b"
                r".{0,80}\b(?:report(?:ed)?|document(?:ed)?|provide(?:d)?|"
                r"measure(?:d)?|state(?:d)?|record(?:ed)?|give|include(?:d)?)\b"
                r".{0,50}\b(?:results?|outcomes?|impacts?|effects?)\b",
                folded,
            )
            or re.search(
                r"\b(?:no|not|never|without)\b.{0,40}\b"
                r"(?:results?|outcomes?|impacts?|effects?)\b.{0,40}\b"
                r"(?:reported|documented|provided|measured|stated|recorded|available)\b",
                folded,
            )
        )
        has_measured_change = bool(
            re.search(
                r"\b(?:increased|decreased|improved|reduced|rose|fell|grew|"
                r"declined|dropped|reached|achieved|remained|measured|"
                r"resulted|yielded)\b",
                folded,
            )
            or re.search(
                r"\b(?:results?|outcomes?|effects?|impacts?)\b.{0,40}\b"
                r"(?:mixed|inconclusive|positive|negative|unchanged)\b",
                folded,
            )
        )
        return reports_absence or has_measured_change
    if aspect == "event":
        return bool(re.search(r"\b(launch\w*|introduc\w*|experiment|trial|releas\w*|updat\w*|chang\w*|removed|discontinued|decision|acquired|partnered|rolled out|announced)\b", folded))
    return False


def _query_requires_exact_calendar_day(query: str) -> bool:
    folded = query.casefold()
    return bool(
        re.search(r"\bexact\s+(?:calendar\s+)?(?:date|day)\b", folded)
        or re.search(r"\bcalendar\s+day\b", folded)
    )


def _claim_covers_exact_date(statement: str) -> bool:
    folded = statement.casefold()
    date_pattern = re.compile(
        r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"
        r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2}\b"
        r"|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"[a-z]*\s+(?:19|20)\d{2}\b"
    )
    event_pattern = re.compile(
        r"\b(?:launch\w*|introduc\w*|debut\w*|release\w*|"
        r"became available|made available|started selling)\b"
    )
    for match in date_pattern.finditer(folded):
        context = folded[max(0, match.start() - 80):match.end() + 80]
        if re.search(r"\b(?:published|publication|posted|article date)\b", context):
            continue
        if event_pattern.search(context):
            return True
    return False


def answer_with_evidence(
    db: Session,
    company_id: str,
    query: str,
    limit: int = 5,
    include_external_public: bool = False,
    include_authorized_internal: bool = False,
) -> dict[str, Any]:
    """Answer a question using extractive, citation-verified RAG."""

    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("Company ID is required.")

    if not isinstance(query, str) or len(query.strip()) < 3:
        raise ValueError("Query must contain at least 3 characters.")

    if len(query) > 2000:
        raise ValueError("Query cannot exceed 2000 characters.")

    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20.")

    company = db.get(Company, company_id)

    if company is None:
        raise ValueError("Company not found.")

    try:
        # Retrieve a larger candidate pool so one long document with many
        # near-duplicate chunks does not crowd every other source out.
        internal_candidates = search_similar_chunks(
            db=db,
            query=query,
            company_id=company_id,
            limit=min(limit * 10, 100),
            include_authorized_internal=include_authorized_internal,
        )
        internal_candidates = _filter_internal_candidates_by_focus(
            internal_candidates,
            query=query,
            company_name=company.name,
        )
        internal_results = _diversify_internal_results(
            internal_candidates,
            limit,
        )

        internal_evidence = _prepare_internal_evidence(
            db=db,
            company=company,
            results=internal_results,
        )
        internal_evidence = append_relevant_knowledge_item_passages(
            db,
            company_id=company_id,
            query=query,
            retrieved_passages=internal_evidence,
            include_authorized_internal=include_authorized_internal,
        )

        external_evidence = []

        if include_external_public:
            external_results = search_external_public_chunks(
                db=db,
                query=query,
                exclude_company_id=company_id,
                limit=limit,
            )

            external_evidence = _prepare_external_evidence(
                results=external_results,
                target_company_id=company_id,
            )

    except EmbeddingError:
        raise
    except Exception as exc:
        raise RAGError(
            f"Evidence retrieval failed: {exc}"
        ) from exc

    evidence = internal_evidence + external_evidence

    requested_publication_period = _requested_publication_period(query)
    if requested_publication_period is not None:
        evidence = _filter_evidence_by_publication_period(
            evidence, requested_publication_period
        )
        internal_evidence = [
            item for item in evidence
            if item.get("evidence_scope") in {"internal", "public_company", "authorized_internal"}
        ]
        external_evidence = [
            item for item in evidence
            if item.get("evidence_scope") == "external_public"
        ]

    evidence_by_id = {
        item["source_id"]: item
        for item in evidence
    }
    requested_aspects = _requested_answer_aspects(query)

    base_response = {
        "company_id": company.id,
        "company_name": company.name,
        "query": query,
        "requested_publication_period": (
            {
                "year": requested_publication_period[0],
                "month": requested_publication_period[1],
            }
            if requested_publication_period is not None
            else None
        ),
        "internal_evidence_count": len(internal_evidence),
        "authorized_internal_evidence_count": sum(
            1 for item in internal_evidence
            if item.get("permission_status") == "authorized_internal"
        ),
        "company_public_evidence_count": sum(
            1 for item in internal_evidence
            if item.get("permission_status") == "public"
        ),
        "external_public_evidence_count": len(external_evidence),
        "verified_claims": [],
        "unsupported_claims": [],
        "requested_aspects": [
            {
                "aspect": aspect,
                "status": "not_found_in_verified_evidence",
            }
            for aspect in sorted(requested_aspects)
        ],
        "answer": None,
        "limitations": [
            "Semantic similarity indicates relevance, not factual correctness.",
            "Citation verification checks textual support, not the independent truth of a publisher's statements.",
            "External public evidence describes other companies and does not establish actions taken by the target company.",
            "Chronological sequence does not establish causation.",
            "Unknown or undocumented information is not inferred.",
            "Factual candidates are extracted from retrieved passages; relevant information outside retrieved passages may be missed.",
            (
                "A month/year-specific question is restricted to sources whose recorded publication date falls within that period; sources with unknown publication dates are excluded."
                if requested_publication_period is not None
                else "No publication-period restriction was inferred because the question did not specify a month and year."
            ),
        ],
        "evidence_sources": [
            {
                "source_id": item["source_id"],
                "source_title": item.get("source_title"),
                "source_url": item.get("source_url"),
                "source_company_id": item.get("source_company_id"),
                "source_company_name": item.get("source_company_name"),
                "evidence_scope": item.get("evidence_scope"),
                "permission_status": item.get("permission_status"),
                "publication_date": (
                    item.get("publication_date").isoformat()
                    if isinstance(item.get("publication_date"), datetime)
                    else item.get("publication_date")
                ),
                "publisher": item.get("publisher"),
                "source_type": item.get("source_type"),
                "similarity": item.get("similarity"),
                "chunk_index": item.get("chunk_index"),
            }
            for item in evidence
        ],
    }

    if not evidence:
        base_response["answer"] = (
            "Insufficient evidence was found to answer this question "
            "from the available permitted sources."
        )
        base_response["answer_status"] = "insufficient_evidence"
        return base_response

    claims = _extract_candidate_claims(
        evidence=evidence,
        query=query,
        company_name=company.name,
    )

    if not claims:
        base_response["answer"] = (
            "No sufficiently relevant factual sentences were identified "
            "in the retrieved passages."
        )
        base_response["answer_status"] = "insufficient_evidence"
        return base_response

    source_text_by_id, source_context_by_id = _build_source_maps(
        evidence
    )

    verification_call_failed = False

    try:
        verification_results, verification_error = verify_claim_citations(
            claims=claims,
            source_text_by_id=source_text_by_id,
            source_context_by_id=source_context_by_id,
        )
    except Exception as exc:
        verification_results = {}
        verification_error = str(exc)
        verification_call_failed = True

    verification_unavailable = (
        verification_call_failed
        or _verification_service_unavailable(verification_error)
    )

    verified_claims, unsupported_claims = _build_verified_claims(
        claims=claims,
        verification_results=verification_results or {},
        evidence_by_id=evidence_by_id,
        verification_unavailable=verification_unavailable,
    )

    # Sort verified claims chronologically using only dates that
    # already appear in their source-supported statements.
    verified_claims.sort(key=_claim_chronology_key)

    base_response["verified_claims"] = verified_claims
    base_response["unsupported_claims"] = unsupported_claims

    covered_aspects = {
        aspect
        for aspect in requested_aspects
        if any(
            (
                _claim_covers_exact_date(claim["statement"])
                if aspect == "date" and _query_requires_exact_calendar_day(query)
                else _claim_covers_aspect(claim["statement"], aspect)
            )
            for claim in verified_claims
        )
    }
    base_response["requested_aspects"] = [
        {
            "aspect": aspect,
            "status": (
                "supported" if aspect in covered_aspects
                else "not_found_in_verified_evidence"
            ),
        }
        for aspect in sorted(requested_aspects)
    ]

    if verification_error:
        base_response["verification_error"] = verification_error
        base_response["limitations"].append(
            "Some extracted sentences were not accepted by citation "
            "verification and were excluded from the answer."
        )

    if verified_claims:
        direct_statements = []
        related_statements = []
        seen_statements = set()

        for claim in verified_claims:
            statement = claim["statement"].strip()
            normalized = statement.casefold()

            if normalized in seen_statements:
                continue

            seen_statements.add(normalized)
            if claim.get("relevance_category") == "related_development":
                related_statements.append(statement)
            else:
                direct_statements.append(statement)

        answer_sections = []
        if direct_statements:
            answer_sections.append(
                "Directly relevant evidence: "
                + " ".join(direct_statements)
            )
        if related_statements:
            answer_sections.append(
                "Related developments: "
                + " ".join(related_statements)
            )

        base_response["answer"] = "\n\n".join(answer_sections)
        base_response["answer_status"] = (
            "partially_answered"
            if requested_aspects - covered_aspects
            else "answered_with_verified_evidence"
        )
        if requested_aspects - covered_aspects:
            missing = ", ".join(sorted(requested_aspects - covered_aspects))
            base_response["answer"] += (
                "\n\nInsufficient verified evidence was found for the "
                f"requested aspect(s): {missing}."
            )
            base_response["limitations"].append(
                "Verified evidence did not address every requested aspect; "
                f"no supported answer was found for: {missing}."
            )
    else:
        base_response["answer"] = (
            "Insufficient verified evidence is available to provide "
            "a factual answer. See the unsupported claims and retrieved "
            "sources for context."
        )
        base_response["answer_status"] = (
            "verification_unavailable"
            if verification_unavailable
            else "insufficient_verified_evidence"
        )

    return base_response
