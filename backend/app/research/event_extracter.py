
import time
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import settings


MODEL_NAME = "gemini-3.6-flash"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]


class ExtractedEvent(BaseModel):
    product_name: str | None = None

    event_type: str = Field(
        description="Category of the product or company event"
    )

    title: str = Field(
        description="Short headline describing the event"
    )

    description: str | None = None

    event_date: str | None = Field(
        default=None,
        description="Date the event occurred, in ISO format if known"
    )

    stated_reason: str | None = None
    reported_outcome: str | None = None

    actor: str | None = Field(
        default=None,
        description="Person or organization responsible for the event, if known"
    )

    evidence_quote: str | None = Field(
        default=None,
        description="Exact sentence or passage supporting this event"
    )

    event_status: Literal[
        "announced",
        "occurred",
        "planned",
        "cancelled",
        "uncertain"
    ] = "uncertain"

    evidence_classification: Literal[
        "primary",
        "secondary",
        "unknown"
    ] = "unknown"

    extraction_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that the source explicitly supports this event"
    )


class ExtractedKnowledgeItem(BaseModel):
    item_type: Literal[
        "proposal",
        "decision",
        "concern",
        "feedback",
        "action_item",
        "outcome"
    ]

    title: str = Field(
        description="Short title describing the extracted information"
    )

    description: str = Field(
        description="Complete explanation of what was proposed, decided, raised or reported"
    )

    actor: str | None = Field(
        default=None,
        description="Person or organization responsible for making the statement"
    )

    status: Literal[
        "proposed",
        "approved",
        "rejected",
        "deferred",
        "in_progress",
        "completed",
        "open",
        "resolved",
        "unknown"
    ] = "unknown"

    item_date: str | None = Field(
        default=None,
        description="Date of the statement or activity in ISO format, if known"
    )

    evidence_quote: str = Field(
        description="Exact quotation from the original source supporting this item"
    )

    evidence_classification: Literal[
        "primary",
        "secondary",
        "unknown"
    ] = "unknown"

    extraction_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this item is accurately supported by the source"
    )


class EventExtractionResult(BaseModel):
    events: list[ExtractedEvent] = Field(
        default_factory=list,
        description="Product and company events explicitly supported by the source"
    )

    knowledge_items: list[ExtractedKnowledgeItem] = Field(
        default_factory=list,
        description="Proposals, decisions, concerns, feedback, action items and outcomes"
    )


client = None


def _get_client():
    global client
    if client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=30000),
        )
    return client


def _has_source_quote(quote: str | None, source_text: str) -> bool:
    if not quote:
        return False
    normalized_source = " ".join(source_text.split()).casefold()
    normalized_quote = " ".join(quote.split()).casefold()
    return bool(normalized_quote and normalized_quote in normalized_source)


def extract_events(
    company_name: str,
    source_text: str,
    source_type: str = "webpage",
    source_title: str | None = None,
    source_kind: str = "public",
    is_synthetic: bool = False,
) -> EventExtractionResult:

    if not source_text or not source_text.strip():
        return EventExtractionResult()

    prompt = f"""
You are an expert company research and knowledge extraction analyst
working for NEXUS.

Your task is to carefully analyze the supplied source about
{company_name}.

SOURCE TYPE:
{source_type}

SOURCE TITLE:
{source_title or "Unknown"}

SOURCE ORIGIN:
{source_kind} {"(synthetic demo data)" if is_synthetic else ""}

SOURCE CONTENT:

{source_text[:30000]}

============================================================
PART 1: EXTRACT COMPANY AND PRODUCT EVENTS
============================================================

Identify genuine events explicitly supported by the source.

Examples:
- Product launches
- Product updates
- New features
- Partnerships
- Acquisitions
- Leadership changes
- Funding announcements
- Product discontinuations
- Experiments, their results, and product failures
- Product improvements supported by the source
- Strategic decisions
- Major company developments

For every event, extract:
1. product_name
2. event_type
3. title
4. description
5. event_date
6. stated_reason
7. reported_outcome
8. actor
9. evidence_quote
10. event_status
11. evidence_classification
12. extraction_confidence

============================================================
PART 2: EXTRACT OTHER KNOWLEDGE
============================================================

Identify:
A. PROPOSALS
B. DECISIONS
C. CONCERNS
D. FEEDBACK
E. ACTION ITEMS
F. OUTCOMES

Rules:
1. Extract only information supported by source.
2. Never invent names, dates, quotations, decisions, reasons, outcomes, measurements.
3. Preserve suggested/discussed/approved/rejected/implemented/completed.
4. Attribute actual speaker if source identifies them.
5. evidence_quote MUST be exact passage from source.
6. Every item must have its own supporting quotation.
7. Do not combine unrelated statements.
8. Avoid duplicates.
9. If conflicting opinions, preserve separately.
10. Missing dates => null.
11. Missing knowledge type => empty list.
12. Do not treat hypothetical plans/assumptions as completed events.
13. Complete understandable sentences.
14. Do not assume internal discussion = official company position.
15. Evidence classification:
   primary = direct original org/participant/official document/first-hand source
   secondary = another source reports/interprets
   unknown = origin cannot be established
16. Confidence 0-1 reflects extraction support, not objective truth.

Return valid structured response containing events and knowledge_items.
"""

    for attempt in range(MAX_RETRIES + 1):

        try:
            print(
                f"Extracting knowledge from {source_type} "
                f"(attempt {attempt + 1}/{MAX_RETRIES + 1})...",
                flush=True,
            )

            response = _get_client().models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EventExtractionResult,
                    temperature=0.1,
                ),
            )

            print("Gemini response received!", flush=True)

            result = response.parsed

            if result is None:
                raise ValueError(
                    "Gemini did not return a valid structured response"
                )

            result.events = [
                event
                for event in result.events
                if _has_source_quote(event.evidence_quote, source_text)
            ]
            result.knowledge_items = [
                item
                for item in result.knowledge_items
                if _has_source_quote(item.evidence_quote, source_text)
            ]

            print(
                f"Events extracted: {len(result.events)}",
                flush=True,
            )

            print(
                f"Knowledge items extracted: {len(result.knowledge_items)}",
                flush=True,
            )

            return result

        except Exception as error:

            error_text = str(error)

            is_retryable = any(
                code in error_text
                for code in ["503", "UNAVAILABLE", "429", "500", "502", "504"]
            )

            if is_retryable and attempt < MAX_RETRIES:

                delay = RETRY_DELAYS[attempt]

                print(
                    f"Gemini temporarily unavailable. "
                    f"Retrying in {delay} seconds...",
                    flush=True,
                )

                time.sleep(delay)

                continue

            print(
                f"Knowledge extraction failed: {error}",
                flush=True,
            )

            raise
