
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = None
    industry: str | None = Field(default=None, max_length=255)
    description: str | None = None


class CompanyOut(BaseModel):
    id: str
    name: str
    website: str | None
    industry: str | None
    description: str | None
    research_status: str
    created_at: datetime
    updated_at: datetime

    @field_validator("research_status", mode="before")
    @classmethod
    def normalize_legacy_pending_status(cls, value: str) -> str:
        # Existing rows may contain the pre-contract ORM default. Normalize
        # only the API representation; never rewrite persisted user data.
        return "not_started" if value == "pending" else value

    model_config = ConfigDict(from_attributes=True)


class SourceOut(BaseModel):
    id: str
    company_id: str
    url: str
    publisher: str | None
    title: str | None
    publication_date: datetime | None
    event_date: datetime | None = None
    source_type: str
    processing_status: str
    collected_at: datetime | None = None
    permission_status: str | None = None
    content_excerpt: str | None = None
    evidence_origin: str | None = None
    source_classification: str | None = None
    content_kind: str | None = None
    discovery_method: str | None = None
    original_url: str | None = None
    extracted_event_evidence: list[dict[str, Any]] = Field(default_factory=list)
    processing_failed_stage: str | None = None
    processing_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EventOut(BaseModel):
    id: str
    company_id: str
    product_name: str | None
    event_type: str
    title: str
    description: str | None
    event_date: datetime | None
    stated_reason: str | None
    reported_outcome: str | None
    evidence_classification: str
    source_ids: list[str]

    model_config = ConfigDict(from_attributes=True)


class KnowledgeItemOut(BaseModel):
    id: str
    company_id: str
    source_id: str
    item_type: str
    title: str
    description: str
    subject_name: str | None
    actor: str | None
    status: str
    item_date: datetime | None
    evidence_quote: str
    evidence_classification: str
    extraction_confidence: float | None
    created_at: datetime
    collected_at: datetime
    source_title: str | None = None
    source_url: str | None = None
    permission_status: str
    evidence_origin: str
    is_synthetic: bool = False


class ProposalCreateIn(BaseModel):
    company_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=20)


class ProposalAnalyzeIn(BaseModel):
    company_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=20)
    proposal_id: str | None = Field(
        default=None,
        description=(
            "Attach this analysis to an already saved proposal belonging to "
            "the same company."
        ),
    )
    include_fresh_external_research: bool = Field(
        default=False,
        description=(
            "Run a bounded public competitor search before analysis. "
            "When false, use relevant public evidence already collected."
        ),
    )
    include_authorized_internal: bool = Field(
        default=False,
        description=(
            "Include authorized internal source documents. This is only "
            "available when the API explicitly enables local internal access."
        ),
    )


class FeedbackCreate(BaseModel):
    company_id: str
    text: str = Field(min_length=1, max_length=10000)
    product_name: str | None = Field(default=None, max_length=255)
    source_id: str | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    external_reference: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=40)
    source_type: str = "user_upload"
    rating: float | None = Field(default=None, ge=0, le=5)
    created_at_source: datetime | None = None
    # Backward-compatible name used by the existing frontend.
    feedback_date: datetime | None = None
