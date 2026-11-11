from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# COMPANY SCHEMAS
# ============================================================

class CompanyCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    website: str | None = None

    description: str | None = None


class CompanyOut(BaseModel):
    id: str
    name: str
    website: str | None
    description: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================================
# EXTERNAL / PUBLIC SOURCE SCHEMA
# ============================================================

class SourceOut(BaseModel):
    """
    Data returned by the API for a public/external source.

    This includes enough information for later components
    such as evidence ranking and RAG.
    """

    id: str

    company_id: str

    url: str

    publisher: str | None

    title: str | None

    # When the source itself was published.
    publication_date: datetime | None

    # When the event described by the source happened.
    event_date: datetime | None

    # Type of source:
    #
    # company_website
    # company_blog
    # press_release
    # news
    # report
    # interview
    # regulatory_filing
    # etc.
    source_type: str

    # Who owns/publishes this source.
    #
    # target_company
    # other_company
    # regulator
    # government
    # news_organization
    # research_organization
    # unknown
    source_owner_type: str

    # True if this is an official source
    # belonging to the company being researched.
    is_target_company_official: bool

    # True if this is an official source
    # belonging to another relevant company/organization.
    is_other_company_official: bool

    # Authority level:
    #
    # 1 = official primary source
    # 2 = government/regulatory/authoritative
    # 3 = reputable secondary source
    # 4 = other public source
    source_authority_level: int

    # How NEXUS discovered this source.
    #
    # website_crawl
    # search_engine
    # news_search
    # public_api
    # manual
    discovery_method: str | None

    # Search query that caused this source
    # to be discovered.
    search_query: str | None

    # Actual extracted webpage/document text.
    content_text: str | None

    processing_status: str

    # When NEXUS collected the source.
    collected_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================================
# EVENT SCHEMA
# ============================================================

class EventOut(BaseModel):
    """
    Structured event extracted from public or internal evidence.
    """

    id: str

    company_id: str

    product_name: str | None

    event_type: str

    title: str

    description: str | None

    event_date: datetime | None

    stated_reason: str | None

    reported_outcome: str | None

    # primary
    # secondary
    # unknown
    evidence_classification: str

    # IDs of all sources supporting this event.
    source_ids: list[str]

    # AI confidence in the extraction.
    extraction_confidence: float | None

    # When this structured event was created
    # in NEXUS.
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================================
# PROPOSAL SCHEMA
# ============================================================

class ProposalAnalyzeIn(BaseModel):
    company_id: str

    title: str = Field(
        min_length=1,
        max_length=500,
    )

    description: str = Field(
        min_length=20,
    )


# ============================================================
# FEEDBACK SCHEMA
# ============================================================

class FeedbackCreate(BaseModel):
    company_id: str

    text: str = Field(
        min_length=1,
    )

    product_name: str | None = None

    source_url: str | None = None

    source_type: str = "user_upload"

    rating: float | None = Field(
        default=None,
        ge=0,
        le=5,
    )

    feedback_date: datetime | None = None