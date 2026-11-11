
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    Boolean,
    Integer,
)

from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def new_id() -> str:
    """Generate a unique ID for a database record."""
    return str(uuid.uuid4())


def utc_now():
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


# ============================================================
# COMPANY
# ============================================================

class Company(Base):

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
    )

    website: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


# ============================================================
# EXTERNAL / PUBLIC SOURCES
# ============================================================

class SourceDocument(Base):

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    url: Mapped[str] = mapped_column(
        String(1000),
    )

    publisher: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_owner_type: Mapped[str] = mapped_column(
        String(50),
        default="unknown",
    )

    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_target_company_official: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    is_other_company_official: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    source_authority_level: Mapped[int] = mapped_column(
        Integer,
        default=4,
    )

    source_type: Mapped[str] = mapped_column(
        String(80),
        default="unknown",
    )

    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    event_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    discovery_method: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    search_query: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    content_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
    )

    content_kind: Mapped[str] = mapped_column(
        String(40),
        default="full_page",
    )

    fetch_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extraction_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


# ============================================================
# INTERNAL SOURCES
# ============================================================

class InternalSource(Base):

    __tablename__ = "internal_sources"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(40),
    )

    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    content_text: Mapped[str] = mapped_column(
        Text,
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    author: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    processing_status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
    )

    source_identifier: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    extraction_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    is_synthetic: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


# ============================================================
# PRODUCT / COMPANY EVENTS
# ============================================================

class ProductEvent(Base):

    __tablename__ = "product_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    product_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
    )

    title: Mapped[str] = mapped_column(
        String(500),
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    event_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    stated_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reported_outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    actor: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    evidence_quote: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    event_status: Mapped[str] = mapped_column(
        String(40),
        default="uncertain",
    )

    evidence_classification: Mapped[str] = mapped_column(
        String(40),
        default="unknown",
    )

    # Original source IDs.
    source_ids: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    # Detailed source references.
    # Each entry identifies internal/external provenance.
    source_references: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    extraction_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


# ============================================================
# EVENT RELATIONSHIPS
# ============================================================

class EventRelationship(Base):

    __tablename__ = "event_relationships"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    from_event_id: Mapped[str] = mapped_column(
        ForeignKey("product_events.id"),
        index=True,
    )

    to_event_id: Mapped[str] = mapped_column(
        ForeignKey("product_events.id"),
        index=True,
    )

    relation_type: Mapped[str] = mapped_column(
        String(80),
    )

    evidence_classification: Mapped[str] = mapped_column(
        String(40),
        default="unknown",
    )

    source_ids: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ============================================================
# PROPOSALS
# ============================================================

class Proposal(Base):

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
    )

    description: Mapped[str] = mapped_column(
        Text,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        default="submitted",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


# ============================================================
# CUSTOMER FEEDBACK
# ============================================================

class Feedback(Base):

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    product_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    text: Mapped[str] = mapped_column(
        Text,
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(80),
        default="user_upload",
    )

    rating: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    sentiment: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    topic: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    feedback_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


# ============================================================
# EXTRACTED KNOWLEDGE ITEMS
# ============================================================

class KnowledgeItem(Base):

    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(40),
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
    )

    description: Mapped[str] = mapped_column(
        Text,
    )

    actor: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        default="unknown",
    )

    item_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    evidence_quote: Mapped[str] = mapped_column(
        Text,
    )

    source_kind: Mapped[str] = mapped_column(
        String(20),
    )

    source_type: Mapped[str] = mapped_column(
        String(80),
    )

    # References either internal_sources.id
    # or source_documents.id.
    source_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
    )

    evidence_classification: Mapped[str] = mapped_column(
        String(40),
        default="unknown",
    )

    extraction_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
