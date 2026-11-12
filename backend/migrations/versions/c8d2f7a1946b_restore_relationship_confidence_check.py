"""restore relationship confidence range constraint

Revision ID: c8d2f7a1946b
Revises: b7c4e91a2f63
"""

import re

from alembic import op
import sqlalchemy as sa


revision = "c8d2f7a1946b"
down_revision = "b7c4e91a2f63"
branch_labels = None
depends_on = None

TABLE_NAME = "event_relationships"
CONSTRAINT_NAME = "ck_event_relationships_confidence_range"
CONSTRAINT_SQL = "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)"


def _normalize_check_sql(value: str) -> str:
    return re.sub(r'[\s()"`\[\]]+', "", value).casefold()


def _has_confidence_check(connection) -> bool:
    inspector = sa.inspect(connection)
    checks = inspector.get_check_constraints(TABLE_NAME)
    expected = _normalize_check_sql(CONSTRAINT_SQL)
    return any(
        _normalize_check_sql(item.get("sqltext") or "") == expected
        for item in checks
    )


def _refuse_invalid_existing_values(connection) -> None:
    invalid_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM event_relationships "
            "WHERE confidence IS NOT NULL "
            "AND (confidence < 0 OR confidence > 1)"
        )
    ).scalar_one()
    if invalid_count:
        raise RuntimeError(
            "Migration stopped without changing data: "
            f"{invalid_count} event relationship(s) have confidence "
            "outside the allowed 0..1 range. Review those records and "
            "rerun the migration after resolving them."
        )


def upgrade() -> None:
    connection = op.get_bind()
    _refuse_invalid_existing_values(connection)

    # On databases where the original anonymous check survived, do not add
    # a duplicate. SQLite's earlier batch recreation drops it, so this
    # forward revision restores the named equivalent there.
    if not _has_confidence_check(connection):
        with op.batch_alter_table(TABLE_NAME, recreate="auto") as batch_op:
            batch_op.create_check_constraint(CONSTRAINT_NAME, CONSTRAINT_SQL)


def downgrade() -> None:
    connection = op.get_bind()
    named_check_exists = any(
        item.get("name") == CONSTRAINT_NAME
        for item in sa.inspect(connection).get_check_constraints(TABLE_NAME)
    )
    if named_check_exists:
        with op.batch_alter_table(TABLE_NAME, recreate="auto") as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
