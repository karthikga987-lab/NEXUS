
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    Table,
    Column,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.db.session import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


# Many-to-many association tables

event_sources = Table(
    "event_sources",
    Base.metadata,
    Column(
        "event_id",
        String(36),
        ForeignKey("product_events.id"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("source_documents.id"),
        primary_key=True,
    ),
)

feedback_topics = Table(
    "feedback_topics",
    Base.metadata,
    Column(
        "feedback_id",
        String(36),
        ForeignKey("feedback.id"),
        primary_key=True,
    ),
    Column("topic", String(255), primary_key=True),
)

analysis_events = Table(
    "analysis_events",
    Base.metadata,
    Column(
        "analysis_id",
        String(36),
        ForeignKey("proposal_analyses.id"),
        primary_key=True,
    ),
    Column(
        "event_id",
        String(36),
        ForeignKey("product_events.id"),
        primary_key=True,
    ),
)

analysis_feedback = Table(
    "analysis_feedback",
    Base.metadata,
    Column(
        "analysis_id",
        String(36),
        ForeignKey("proposal_analyses.id"),
        primary_key=True,
    ),
    Column(
        "feedback_id",
        String(36),
        ForeignKey("feedback.id"),
        primary_key=True,
    ),
)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    website: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    industry: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    research_status: Mapped[str] = mapped_column(
        String(40), default="not_started"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ResearchRun(Base):
    """Persisted summary counters for one bounded company research run."""

    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_summary: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    publisher: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        String(80), default="other"
    )
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    content_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    permission_status: Mapped[str] = mapped_column(
        String(40), default="public"
    )
    reliability: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    processing_status: Mapped[str] = mapped_column(
        String(40), default="pending"
    )
    source_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )

    @property
    def original_url(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        return metadata.get("original_url", self.url)

    @property
    def content_excerpt(self) -> str | None:
        return (self.content_text or "")[:1200] or None

    @property
    def evidence_origin(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        return metadata.get("evidence_origin", "public_company" if self.permission_status == "public" else "authorized_internal")

    @property
    def source_classification(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        return metadata.get("source_category", "company_page")

    @property
    def content_kind(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        return metadata.get("content_kind", "full_document")

    @property
    def discovery_method(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        return metadata.get("discovery_method")

    @property
    def extracted_event_evidence(self) -> list[dict]:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        evidence = metadata.get("extracted_event_evidence")
        return evidence if isinstance(evidence, list) else []

    @property
    def processing_failed_stage(self) -> str | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        value = metadata.get("ingestion_failed_stage")
        allowed = {
            "source_validation",
            "source_initialization",
            "embedding",
            "event_extraction",
            "event_persistence",
            "knowledge_item_persistence",
            "finalization",
        }
        return value if isinstance(value, str) and value in allowed else None

    @property
    def processing_error(self) -> str | None:
        if self.processing_status != "failed":
            return None
        messages = {
            "source_validation": "The saved document has no usable text content.",
            "source_initialization": "The source could not enter document processing.",
            "embedding": "Embedding generation failed; check the configured embedding service and model.",
            "event_extraction": "Structured event extraction failed; check the configured Ollama model and response format.",
            "event_persistence": "An extracted event did not pass persistence validation.",
            "knowledge_item_persistence": "An extracted knowledge item failed persistence or exact-quote validation.",
            "finalization": "Document processing could not be finalized.",
        }
        return messages.get(
            self.processing_failed_stage,
            "Document processing failed; the detailed internal error is not exposed by this endpoint.",
        )

    @property
    def event_date(self) -> datetime | None:
        metadata = self.source_metadata if isinstance(self.source_metadata, dict) else {}
        entries = metadata.get("extracted_event_evidence")
        if isinstance(entries, list):
            if len(entries) == 1 and isinstance(entries[0], dict):
                raw_value = entries[0].get("event_date")
            else:
                return None
        else:
            raw_value = metadata.get("event_date")
        if not isinstance(raw_value, str):
            return None
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None


class KnowledgeItem(Base):
    """Evidence-linked company knowledge that is not necessarily an event."""

    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('proposal', 'decision', 'concern', 'feedback', "
            "'action_item', 'outcome')",
            name="ck_knowledge_items_type",
        ),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'deferred', "
            "'in_progress', 'completed', 'open', 'resolved', 'unknown')",
            name="ck_knowledge_items_status",
        ),
        CheckConstraint(
            "evidence_classification IN ('documented', 'supported', "
            "'correlation', 'inference', 'unknown')",
            name="ck_knowledge_items_evidence_classification",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR "
            "(extraction_confidence >= 0 AND extraction_confidence <= 1)",
            name="ck_knowledge_items_confidence_range",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    subject_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    actor: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    item_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_quote: Mapped[str] = mapped_column(Text)
    evidence_classification: Mapped[str] = mapped_column(
        String(40), default="documented"
    )
    extraction_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class ProductEvent(Base):
    __tablename__ = "product_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    event_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stated_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    reported_outcome: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    evidence_classification: Mapped[str] = mapped_column(
        String(40), default="unknown"
    )
    extraction_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class EventRelationship(Base):
    __tablename__ = "event_relationships"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    from_event_id: Mapped[str] = mapped_column(
        ForeignKey("product_events.id"), index=True
    )
    to_event_id: Mapped[str] = mapped_column(
        ForeignKey("product_events.id"), index=True
    )

    # Contract names map to the existing database column names.
    relationship_type: Mapped[str] = mapped_column(
        "relation_type", String(80)
    )
    evidence_status: Mapped[str] = mapped_column(
        "evidence_classification",
        String(40),
        default="unknown",
    )

    # Backward-compatible aliases for existing Python code.
    relation_type = synonym("relationship_type")
    evidence_classification = synonym("evidence_status")

    explanation: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0 AND confidence <= 1)"
        ),
    )


# Relationship-to-source provenance.
# One relationship can be supported by multiple source documents.
# Each source has one retained quotation per relationship.

relationship_sources = Table(
    "relationship_sources",
    Base.metadata,
    Column(
        "relationship_id",
        String(36),
        ForeignKey("event_relationships.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("supporting_quote", Text, nullable=False),
    Column("verification_method", String(100), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    ),
)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    feedback_text: Mapped[str] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    language: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    sentiment: Mapped[str] = mapped_column(
        String(40), default="unknown"
    )
    feedback_type: Mapped[str] = mapped_column(
        String(80), default="other"
    )
    analysis_status: Mapped[str] = mapped_column(
        String(40), default="pending"
    )


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(40), default="submitted"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ProposalAnalysis(Base):
    __tablename__ = "proposal_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.id"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(40), default="queued"
    )
    recommendation: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    limitations: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    risks: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_analyses.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id")
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_events.id"), nullable=True
    )
    claim: Mapped[str] = mapped_column(Text)
    evidence_classification: Mapped[str] = mapped_column(
        String(40), default="unknown"
    )


class ProposalAnalysisSnapshot(Base):
    """Immutable analysis-time context needed to reopen saved analyses."""

    __tablename__ = "proposal_analysis_snapshots"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_analyses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
