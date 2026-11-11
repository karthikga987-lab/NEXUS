
"""add source metadata and internal sources

Revision ID: 9efb883e2836
Revises:
Create Date: 2026-11-11 19:21:08.592978
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers
revision: str = "9efb883e2836"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply database schema changes."""

    # 1. Create the new internal_sources table.
    op.create_table(
        "internal_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Add an index for faster company-based lookups.
    op.create_index(
        op.f("ix_internal_sources_company_id"),
        "internal_sources",
        ["company_id"],
        unique=False,
    )

    # 3. Add metadata columns to existing source_documents.
    # Server defaults allow existing records to remain valid.

    op.add_column(
        "source_documents",
        sa.Column(
            "source_owner_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    op.add_column(
        "source_documents",
        sa.Column(
            "is_target_company_official",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "source_documents",
        sa.Column(
            "is_other_company_official",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "source_documents",
        sa.Column(
            "source_authority_level",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("4"),
        ),
    )

    op.add_column(
        "source_documents",
        sa.Column(
            "discovery_method",
            sa.String(length=80),
            nullable=True,
        ),
    )

    op.add_column(
        "source_documents",
        sa.Column(
            "search_query",
            sa.String(length=1000),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Reverse the database schema changes."""

    # 1. Remove the added source_documents columns.
    op.drop_column("source_documents", "search_query")
    op.drop_column("source_documents", "discovery_method")
    op.drop_column("source_documents", "source_authority_level")
    op.drop_column("source_documents", "is_other_company_official")
    op.drop_column("source_documents", "is_target_company_official")
    op.drop_column("source_documents", "source_owner_type")

    # 2. Remove the internal_sources index and table.
    op.drop_index(
        op.f("ix_internal_sources_company_id"),
        table_name="internal_sources",
    )

    op.drop_table("internal_sources")
