"""Pytest fixtures shared across the test suite.

Each test gets its own SQLite file under a tmp directory. We rewrite
`config.DB_PATH` and reset the thread-local connection so the next call to
`db.get_connection()` opens the fresh DB. Schema is created via `init_db()`.
"""

from __future__ import annotations

import pytest

from app import config, db


@pytest.fixture(autouse=True)
def _temp_sqlite_db(tmp_path, monkeypatch):
    """Point the SQLite store at a per-test temp file and initialize schema."""
    db_file = tmp_path / "test_sudoku.db"
    monkeypatch.setattr(config, "DB_PATH", str(db_file))
    # Drop any connection inherited from a previous test (it points at the
    # old DB_PATH) so the next get_connection() opens the new file.
    db.reset_connection()
    db.init_db()
    yield
    # Tear down: close the connection so the temp file isn't held open while
    # pytest cleans up tmp_path.
    db.reset_connection()
