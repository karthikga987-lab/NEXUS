"""add source ingestion metadata

Revision ID: 6a0d4b719c21
Revises: 0ac08409d00a
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a0d4b719c21"
down_revision: Union[str, Sequence[str], None] = "0ac08409d00a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("content_kind", sa.String(40), nullable=False,
                  server_default="full_page"),
    )
    op.add_column(
        "source_documents",
        sa.Column("fetch_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("extraction_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE source_documents SET updated_at = collected_at "
        "WHERE updated_at IS NULL"
    )

    op.add_column(
        "internal_sources",
        sa.Column("source_identifier", sa.String(255), nullable=True),
    )
    op.add_column(
        "internal_sources",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "internal_sources",
        sa.Column("extraction_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_internal_sources_content_hash",
        "internal_sources",
        ["content_hash"],
        unique=False,
    )
    op.add_column(
        "internal_sources",
        sa.Column("is_synthetic", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.execute(
        "UPDATE internal_sources SET is_synthetic = 1 "
        "WHERE title LIKE '[SYNTHETIC DEMO]%'"
    )
    op.add_column(
        "internal_sources",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE internal_sources SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("internal_sources", "updated_at")
    op.drop_column("internal_sources", "is_synthetic")
    op.drop_index("ix_internal_sources_content_hash", table_name="internal_sources")
    op.drop_column("internal_sources", "extraction_hash")
    op.drop_column("internal_sources", "content_hash")
    op.drop_column("internal_sources", "source_identifier")
    op.drop_column("source_documents", "updated_at")
    op.drop_column("source_documents", "fetch_error")
    op.drop_column("source_documents", "extraction_hash")
    op.drop_column("source_documents", "content_kind")
