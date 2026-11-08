from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = None
    description: str | None = None

class CompanyOut(BaseModel):
    id: str
    name: str
    website: str | None
    description: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SourceOut(BaseModel):
    id: str
    company_id: str
    url: str
    publisher: str | None
    title: str | None
    publication_date: datetime | None
    event_date: datetime | None
    source_type: str
    processing_status: str
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

class ProposalAnalyzeIn(BaseModel):
    company_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=20)

class FeedbackCreate(BaseModel):
    company_id: str
    text: str = Field(min_length=1)
    product_name: str | None = None
    source_url: str | None = None
    source_type: str = "user_upload"
    rating: float | None = Field(default=None, ge=0, le=5)
    feedback_date: datetime | None = None
