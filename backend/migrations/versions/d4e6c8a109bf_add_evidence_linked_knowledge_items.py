"""add evidence-linked knowledge items and research-run summaries

Revision ID: d4e6c8a109bf
Revises: c8d2f7a1946b
Create Date: 2026-11-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e6c8a109bf"
down_revision: Union[str, Sequence[str], None] = "c8d2f7a1946b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new tables; existing tables and rows are left untouched."""
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("failure_summary", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_runs_company_id",
        "research_runs",
        ["company_id"],
    )

    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("item_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column(
            "evidence_classification",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_type IN ('proposal', 'decision', 'concern', 'feedback', "
            "'action_item', 'outcome')",
            name="ck_knowledge_items_type",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'deferred', "
            "'in_progress', 'completed', 'open', 'resolved', 'unknown')",
            name="ck_knowledge_items_status",
        ),
        sa.CheckConstraint(
            "evidence_classification IN ('documented', 'supported', "
            "'correlation', 'inference', 'unknown')",
            name="ck_knowledge_items_evidence_classification",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR "
            "(extraction_confidence >= 0 AND extraction_confidence <= 1)",
            name="ck_knowledge_items_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_items_company_id",
        "knowledge_items",
        ["company_id"],
    )
    op.create_index(
        "ix_knowledge_items_source_id",
        "knowledge_items",
        ["source_id"],
    )
    op.create_index(
        "ix_knowledge_items_item_type",
        "knowledge_items",
        ["item_type"],
    )


def downgrade() -> None:
    """Refuse to discard collected research data; empty rollback is safe."""
    connection = op.get_bind()
    knowledge_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_items")
    ).scalar_one()
    research_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM research_runs")
    ).scalar_one()
    if knowledge_count or research_count:
        raise RuntimeError(
            "Downgrade refused: knowledge_items or research_runs contains "
            "data. Export or migrate those rows before downgrading."
        )

    op.drop_index("ix_research_runs_company_id", table_name="research_runs")
    op.drop_table("research_runs")
    op.drop_index("ix_knowledge_items_item_type", table_name="knowledge_items")
    op.drop_index("ix_knowledge_items_source_id", table_name="knowledge_items")
    op.drop_index("ix_knowledge_items_company_id", table_name="knowledge_items")
    op.drop_table("knowledge_items")
