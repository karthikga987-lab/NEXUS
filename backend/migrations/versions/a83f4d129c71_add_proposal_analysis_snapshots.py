"""add immutable proposal analysis evidence snapshots

Revision ID: a83f4d129c71
Revises: d4e6c8a109bf
Create Date: 2026-11-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a83f4d129c71"
down_revision: Union[str, Sequence[str], None] = "d4e6c8a109bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create a new empty snapshot table; no existing records are rewritten."""
    op.create_table(
        "proposal_analysis_snapshots",
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["proposal_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("analysis_id"),
    )


def downgrade() -> None:
    """Refuse to drop snapshots after they contain user data."""
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT COUNT(*) FROM proposal_analysis_snapshots")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Downgrade refused: proposal analysis snapshots contain data. "
            "Export or migrate those snapshots before downgrading."
        )
    op.drop_table("proposal_analysis_snapshots")
