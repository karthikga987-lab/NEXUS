
"""add relationship company ownership and source provenance

Revision ID: b7c4e91a2f63
Revises: e02a9b9d1e2e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c4e91a2f63"
down_revision: Union[str, Sequence[str], None] = "e02a9b9d1e2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add company_id as nullable first so existing relationships survive.
    op.add_column(
        "event_relationships",
        sa.Column("company_id", sa.String(length=36), nullable=True),
    )

    # Backfill company ownership using the source event.
    op.execute(
        sa.text(
            """
            UPDATE event_relationships
            SET company_id = (
                SELECT product_events.company_id
                FROM product_events
                WHERE product_events.id =
                    event_relationships.from_event_id
            )
            """
        )
    )

    # Refuse to continue if either endpoint is missing or belongs
    # to a different company. Never silently assign cross-company links.
    connection = op.get_bind()

    missing_owner_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM event_relationships
            WHERE company_id IS NULL
            """
        )
    ).scalar_one()

    cross_company_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM event_relationships AS r
            JOIN product_events AS target_event
                ON target_event.id = r.to_event_id
            WHERE target_event.company_id != r.company_id
            """
        )
    ).scalar_one()

    if missing_owner_count:
        raise RuntimeError(
            "Migration stopped: "
            f"{missing_owner_count} relationships could not be assigned "
            "to a company from their source event."
        )

    if cross_company_count:
        raise RuntimeError(
            "Migration stopped: "
            f"{cross_company_count} relationships connect events "
            "from different companies. Review these records first."
        )

    # SQLite requires batch mode for safe NOT NULL and FK changes.
    with op.batch_alter_table(
        "event_relationships",
        recreate="auto",
    ) as batch_op:
        batch_op.alter_column(
            "company_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_event_relationships_company_id_companies",
            "companies",
            ["company_id"],
            ["id"],
        )

    op.create_index(
        "ix_event_relationships_company_id",
        "event_relationships",
        ["company_id"],
        unique=False,
    )

    # Persist relationship provenance separately from the relationship.
    op.create_table(
        "relationship_sources",
        sa.Column("relationship_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("supporting_quote", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["relationship_id"],
            ["event_relationships.id"],
            name="fk_relationship_sources_relationship_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_documents.id"],
            name="fk_relationship_sources_source_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("relationship_id", "source_id"),
    )


def downgrade() -> None:
    op.drop_table("relationship_sources")

    op.drop_index(
        "ix_event_relationships_company_id",
        table_name="event_relationships",
    )

    with op.batch_alter_table(
        "event_relationships",
        recreate="auto",
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_event_relationships_company_id_companies",
            type_="foreignkey",
        )
        batch_op.drop_column("company_id")
