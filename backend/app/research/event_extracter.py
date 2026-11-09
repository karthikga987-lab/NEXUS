
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import settings


# 1. Gemini model
MODEL_NAME = "gemini-3.6-flash"


# 2. Structure of a single extracted event
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

    evidence_classification: Literal[
        "primary", "secondary", "unknown"
    ] = "unknown"

    extraction_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this event is explicitly supported by the source"
    )


# 3. Structure of the complete extraction response
class EventExtractionResult(BaseModel):

    events: list[ExtractedEvent] = Field(
        description="Events explicitly supported by the supplied source text"
    )


# 4. Check API key
if not settings.gemini_api_key:
    raise ValueError(
        "GEMINI_API_KEY is missing from environment variables"
    )


# 5. Create Gemini client with timeout
client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(
        timeout=30000
    )
)


# 6. Extract events from source text
def extract_events(
    company_name: str,
    source_text: str
) -> list[ExtractedEvent]:

    if not source_text or not source_text.strip():
        return []

    prompt = f"""
    You are an expert company research analyst.

    Analyze the following webpage content about {company_name}.

    Identify important product-related and company-related events.

    Examples include:
    - Product launches
    - Product updates
    - New features
    - Partnerships
    - Acquisitions
    - Leadership changes
    - Funding announcements
    - Product discontinuations
    - Strategic decisions

    IMPORTANT RULES:

    1. Extract only events explicitly supported by the source.
    2. Do not invent events, dates, reasons or outcomes.
    3. If a detail is unavailable, return null.
    4. Do not treat general descriptions as actual events.
    5. Avoid extracting the same event multiple times.
    6. Return an empty events list if no genuine events exist.
    7. Classify evidence as:
       - primary: information published by the company itself
       - secondary: information reported by another source
       - unknown: source origin cannot be established

    SOURCE CONTENT:

    {source_text[:30000]}
    """

    try:

        print("Sending request to Gemini...", flush=True)

        response = client.models.generate_content(
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

        print(
            f"Number of events extracted: {len(result.events)}",
            flush=True
        )

        return result.events

    except Exception as error:

        print(f"Event extraction failed: {error}", flush=True)

        raise
