import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
OLD_HEAD = "b7c4e91a2f63"


def migrate(database_path, revision="head", command="upgrade"):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def seed_reference_rows(connection):
    connection.execute(
        "INSERT INTO companies "
        "(id, name, research_status, created_at, updated_at) "
        "VALUES ('company', 'Synthetic company', 'not_started', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO product_events "
        "(id, company_id, event_type, title, evidence_classification, "
        "created_at, updated_at) VALUES "
        "('event-a', 'company', 'other', 'Synthetic A', 'unknown', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
        "('event-b', 'company', 'other', 'Synthetic B', 'unknown', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )


def insert_relationship(connection, relationship_id, confidence):
    connection.execute(
        "INSERT INTO event_relationships "
        "(id, company_id, from_event_id, to_event_id, relation_type, "
        "evidence_classification, confidence, created_at) VALUES "
        "(?, 'company', 'event-a', 'event-b', 'PRECEDED_BY', "
        "'correlation', ?, CURRENT_TIMESTAMP)",
        (relationship_id, confidence),
    )


def assert_constraint_and_values(connection, existing_relationship=None):
    table_sql = connection.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'event_relationships'"
    ).fetchone()[0]
    assert "ck_event_relationships_confidence_range" in table_sql
    assert "confidence >= 0" in table_sql
    assert "confidence <= 1" in table_sql

    if existing_relationship is not None:
        assert connection.execute(
            "SELECT confidence FROM event_relationships WHERE id = ?",
            (existing_relationship,),
        ).fetchone() == (0.75,)

    # Boundary values and a middle value remain valid.
    for value in (0.0, 0.5, 1.0, None):
        rid = f"valid-{value}"
        insert_relationship(connection, rid, value)
        connection.execute(
            "DELETE FROM event_relationships WHERE id = ?", (rid,)
        )

    for value in (-0.01, 1.01):
        with pytest.raises(sqlite3.IntegrityError):
            insert_relationship(connection, f"invalid-{value}", value)


def test_fresh_sqlite_database_migrates_from_beginning_with_constraint(tmp_path):
    database_path = tmp_path / "fresh_migration.db"
    migrate(database_path)

    with sqlite3.connect(database_path) as connection:
        seed_reference_rows(connection)
        assert_constraint_and_values(connection)


def test_database_at_previous_head_upgrades_without_losing_data(tmp_path):
    database_path = tmp_path / "previous_head_migration.db"
    migrate(database_path, OLD_HEAD)

    with sqlite3.connect(database_path) as connection:
        seed_reference_rows(connection)
        # This row represents existing user data present before the forward
        # revision is applied. The migration must preserve it unchanged.
        insert_relationship(connection, "existing-relationship", 0.75)
        connection.commit()

    migrate(database_path)

    with sqlite3.connect(database_path) as connection:
        assert_constraint_and_values(
            connection,
            existing_relationship="existing-relationship",
        )


def test_invalid_legacy_value_stops_forward_migration_without_data_loss(tmp_path):
    database_path = tmp_path / "invalid_legacy_data.db"
    migrate(database_path, OLD_HEAD)

    with sqlite3.connect(database_path) as connection:
        seed_reference_rows(connection)
        insert_relationship(connection, "out-of-range-existing", 1.5)
        connection.commit()

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Migration stopped without changing data" in result.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT confidence FROM event_relationships "
            "WHERE id = 'out-of-range-existing'"
        ).fetchone() == (1.5,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (OLD_HEAD,)


def test_downgrade_to_previous_head_preserves_relationship_rows(tmp_path):
    database_path = tmp_path / "downgrade_migration.db"
    migrate(database_path)

    with sqlite3.connect(database_path) as connection:
        seed_reference_rows(connection)
        insert_relationship(connection, "downgrade-preserved", 0.4)
        connection.commit()

    migrate(database_path, OLD_HEAD, command="downgrade")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT confidence FROM event_relationships "
            "WHERE id = 'downgrade-preserved'"
        ).fetchone() == (0.4,)
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'event_relationships'"
        ).fetchone()[0]
        assert "ck_event_relationships_confidence_range" not in table_sql
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (OLD_HEAD,)
