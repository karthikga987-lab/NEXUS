from sqlalchemy import create_engine, event, text

from app.db.session import _enable_sqlite_foreign_keys


def test_sqlite_connection_enforces_declared_cascade_in_temporary_database(tmp_path):
    database_path = tmp_path / "sqlite_foreign_keys.db"
    engine = create_engine(f"sqlite:///{database_path}")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(text(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER "
                "REFERENCES parent(id) ON DELETE CASCADE)"
            ))
            connection.execute(text("INSERT INTO parent (id) VALUES (1)"))
            connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 1)"))
            connection.execute(text("DELETE FROM parent WHERE id=1"))
            assert connection.execute(text("SELECT COUNT(*) FROM child")).scalar_one() == 0
    finally:
        engine.dispose()
