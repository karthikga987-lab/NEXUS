import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    Integer,
    JSON,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def new_embedding_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "chunk_index",
            "model_name",
            name="uq_document_embedding_chunk_model",
        ),
        Index("ix_document_embeddings_source_id", "source_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_embedding_id,
    )

    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    chunk_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    embedding: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="nomic-embed-text",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )