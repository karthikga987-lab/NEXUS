import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "d4e6c8a109bf"
CURRENT_HEAD = "a83f4d129c71"


def migrate(database_path, revision="head", command="upgrade"):
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


def assert_succeeded(result):
    assert result.returncode == 0, result.stdout + result.stderr


def seed_analysis_rows(connection):
    connection.execute(
        "INSERT INTO companies "
        "(id, name, research_status, created_at, updated_at) VALUES "
        "('synthetic-company', '[SYNTHETIC] Snapshot Co', 'not_started', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO proposals "
        "(id, company_id, title, description, status, created_at, updated_at) "
        "VALUES ('synthetic-proposal', 'synthetic-company', "
        "'[SYNTHETIC] Proposal', 'Synthetic migration fixture.', "
        "'submitted', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO proposal_analyses "
        "(id, proposal_id, status, recommendation, limitations, risks, "
        "created_at, completed_at) VALUES ('synthetic-analysis', "
        "'synthetic-proposal', 'completed', 'Synthetic recommendation.', "
        "'[]', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    connection.commit()


def insert_snapshot(connection):
    snapshot = {
        "version": 1,
        "documentary_evidence": [],
        "verified_claims": [],
    }
    connection.execute(
        "INSERT INTO proposal_analysis_snapshots "
        "(analysis_id, snapshot, captured_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        ("synthetic-analysis", json.dumps(snapshot)),
    )
    connection.commit()


def test_fresh_sqlite_database_includes_snapshot_storage(tmp_path):
    path = tmp_path / "fresh_proposal_snapshot.db"
    assert_succeeded(migrate(path))

    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(proposal_analysis_snapshots)"
            )
        }
        assert columns == {"analysis_id", "snapshot", "captured_at"}
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_HEAD,)
        seed_analysis_rows(connection)
        insert_snapshot(connection)
        assert json.loads(connection.execute(
            "SELECT snapshot FROM proposal_analysis_snapshots "
            "WHERE analysis_id='synthetic-analysis'"
        ).fetchone()[0])["version"] == 1


def test_upgrade_from_previous_head_preserves_existing_analysis(tmp_path):
    path = tmp_path / "existing_proposal_analysis.db"
    assert_succeeded(migrate(path, PREVIOUS_HEAD))
    with sqlite3.connect(path) as connection:
        seed_analysis_rows(connection)

    assert_succeeded(migrate(path))

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT title, description FROM proposals "
            "WHERE id='synthetic-proposal'"
        ).fetchone() == (
            "[SYNTHETIC] Proposal",
            "Synthetic migration fixture.",
        )
        assert connection.execute(
            "SELECT recommendation FROM proposal_analyses "
            "WHERE id='synthetic-analysis'"
        ).fetchone() == ("Synthetic recommendation.",)
        insert_snapshot(connection)
        assert connection.execute(
            "SELECT COUNT(*) FROM proposal_analysis_snapshots"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_HEAD,)


def test_downgrade_refuses_to_discard_saved_snapshots(tmp_path):
    path = tmp_path / "snapshot_downgrade_refusal.db"
    assert_succeeded(migrate(path))
    with sqlite3.connect(path) as connection:
        seed_analysis_rows(connection)
        insert_snapshot(connection)

    result = migrate(path, PREVIOUS_HEAD, command="downgrade")
    assert result.returncode != 0
    assert "proposal analysis snapshots contain data" in result.stderr

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM proposal_analysis_snapshots"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_HEAD,)


def test_empty_snapshot_migration_downgrades_without_data_loss(tmp_path):
    path = tmp_path / "empty_snapshot_downgrade.db"
    assert_succeeded(migrate(path))
    assert_succeeded(migrate(path, PREVIOUS_HEAD, command="downgrade"))

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='proposal_analysis_snapshots'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (PREVIOUS_HEAD,)

