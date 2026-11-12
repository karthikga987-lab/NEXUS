import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
CURRENT_OLD_HEAD = "c8d2f7a1946b"
NEW_HEAD = "d4e6c8a109bf"


def run_migration(database_path, revision="head", command="upgrade"):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def assert_migration_succeeded(result):
    assert result.returncode == 0, result.stdout + result.stderr


def seed_company_and_source(connection):
    connection.execute(
        "INSERT INTO companies "
        "(id, name, research_status, created_at, updated_at) VALUES "
        "('company-synthetic', 'Synthetic Migration Co', 'not_started', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO source_documents "
        "(id, company_id, url, title, publisher, source_type, collected_at, "
        "content_text, content_hash, permission_status, reliability, "
        "processing_status) VALUES "
        "('source-synthetic', 'company-synthetic', "
        "'https://synthetic.example/source', 'Synthetic source', "
        "'synthetic.example', 'news', CURRENT_TIMESTAMP, "
        "'The synthetic team approved a pilot.', 'synthetic-hash', "
        "'public', 0.8, 'processed')"
    )
    connection.commit()


def insert_knowledge_item(connection):
    connection.execute(
        "INSERT INTO knowledge_items "
        "(id, company_id, source_id, item_type, title, description, "
        "subject_name, actor, status, item_date, evidence_quote, "
        "evidence_classification, extraction_confidence, created_at, "
        "collected_at) VALUES "
        "('item-synthetic', 'company-synthetic', 'source-synthetic', "
        "'decision', 'Synthetic pilot approval', "
        "'The synthetic team approved a pilot.', 'pilot', 'team', "
        "'approved', NULL, 'The synthetic team approved a pilot.', "
        "'documented', 0.9, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.commit()


def test_fresh_database_migrates_from_beginning_with_additive_tables(tmp_path):
    database_path = tmp_path / "fresh_knowledge_migration.db"
    assert_migration_succeeded(run_migration(database_path))

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "knowledge_items" in tables
        assert "research_runs" in tables
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (NEW_HEAD,)
        seed_company_and_source(connection)
        insert_knowledge_item(connection)
        assert connection.execute(
            "SELECT evidence_quote FROM knowledge_items "
            "WHERE id='item-synthetic'"
        ).fetchone() == ("The synthetic team approved a pilot.",)


def test_old_head_upgrade_preserves_existing_rows_and_adds_knowledge_table(
    tmp_path,
):
    database_path = tmp_path / "existing_c8_database.db"
    assert_migration_succeeded(
        run_migration(database_path, CURRENT_OLD_HEAD)
    )
    with sqlite3.connect(database_path) as connection:
        seed_company_and_source(connection)

    assert_migration_succeeded(run_migration(database_path))

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT name FROM companies WHERE id='company-synthetic'"
        ).fetchone() == ("Synthetic Migration Co",)
        assert connection.execute(
            "SELECT content_text, permission_status FROM source_documents "
            "WHERE id='source-synthetic'"
        ).fetchone() == (
            "The synthetic team approved a pilot.",
            "public",
        )
        insert_knowledge_item(connection)
        assert connection.execute(
            "SELECT COUNT(*) FROM knowledge_items"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (NEW_HEAD,)


def test_knowledge_constraints_reject_invalid_type_and_confidence(tmp_path):
    database_path = tmp_path / "knowledge_constraints.db"
    assert_migration_succeeded(run_migration(database_path))
    with sqlite3.connect(database_path) as connection:
        seed_company_and_source(connection)
        insert_knowledge_item(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE knowledge_items SET extraction_confidence=1.1 "
                "WHERE id='item-synthetic'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE knowledge_items SET item_type='invented' "
                "WHERE id='item-synthetic'"
            )


def test_downgrade_refuses_to_discard_knowledge_rows(tmp_path):
    database_path = tmp_path / "knowledge_downgrade.db"
    assert_migration_succeeded(run_migration(database_path))
    with sqlite3.connect(database_path) as connection:
        seed_company_and_source(connection)
        insert_knowledge_item(connection)

    result = run_migration(
        database_path,
        CURRENT_OLD_HEAD,
        command="downgrade",
    )
    assert result.returncode != 0
    assert "Downgrade refused" in result.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT evidence_quote FROM knowledge_items "
            "WHERE id='item-synthetic'"
        ).fetchone() == ("The synthetic team approved a pilot.",)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (NEW_HEAD,)


def test_empty_additive_migration_can_be_downgraded_safely(tmp_path):
    database_path = tmp_path / "empty_knowledge_downgrade.db"
    assert_migration_succeeded(run_migration(database_path))
    assert_migration_succeeded(
        run_migration(database_path, CURRENT_OLD_HEAD, command="downgrade")
    )
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "knowledge_items" not in tables
        assert "research_runs" not in tables
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_OLD_HEAD,)
