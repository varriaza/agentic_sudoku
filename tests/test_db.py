"""Tests for the SQLite layer in `app/db.py`.

Covers:
- Persistence across simulated server restarts (close + reopen the connection).
- Schema correctness (tables, columns, composite PKs, leaderboard index).
- `init_db()` idempotency.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app import db, puzzle, state


# ---------------------------------------------------------------------------
# 1. Persistence across restarts
# ---------------------------------------------------------------------------

def test_session_and_solve_persist_across_restart():
    today = date(2026, 5, 24)
    date_str = today.isoformat()

    state.get_or_create_session("0xPersist", date_str, "easy")
    state.record_solve(
        "0xPersist", date_str, "easy",
        "Persist1", 60.5, datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )

    # Simulate a server restart: drop the in-memory connection.
    # The DB file at config.DB_PATH stays put.
    db.reset_connection()

    # init_db() is idempotent and is what create_app() would call on startup.
    db.init_db()

    restored = state.get_session("0xPersist", date_str, "easy")
    assert restored is not None
    assert restored["solved"] is True
    assert restored["name"] == "Persist1"
    assert restored["solve_time_seconds"] == 60.5


def test_puzzle_cache_persists_across_restart():
    today = date(2026, 5, 24)
    grid, solution = puzzle.get_cached_puzzle(today, "hard")

    db.reset_connection()
    db.init_db()

    grid2, solution2 = puzzle.get_cached_puzzle(today, "hard")
    assert grid2 == grid
    assert solution2 == solution


def test_leaderboard_persists_across_restart():
    date_str = "2026-05-24"

    for wallet, name, secs, ts in [
        ("0xA", "Alice", 90.0, datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)),
        ("0xB", "Bob",   60.0, datetime(2026, 5, 24, 12, 1, 0, tzinfo=timezone.utc)),
    ]:
        state.get_or_create_session(wallet, date_str, "easy")
        state.record_solve(wallet, date_str, "easy", name, secs, ts)

    db.reset_connection()
    db.init_db()

    lb = state.get_leaderboard(date_str, "easy")
    assert [(e["name"], e["solve_time_seconds"]) for e in lb] == [
        ("Bob", 60.0),
        ("Alice", 90.0),
    ]


# ---------------------------------------------------------------------------
# 2. Schema correctness
# ---------------------------------------------------------------------------

def _table_columns(table: str) -> dict[str, str]:
    conn = db.get_connection()
    return {row["name"]: row["type"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _primary_key(table: str) -> list[str]:
    conn = db.get_connection()
    pk_rows = sorted(
        (row for row in conn.execute(f"PRAGMA table_info({table})") if row["pk"]),
        key=lambda r: r["pk"],
    )
    return [row["name"] for row in pk_rows]


def test_puzzles_table_columns():
    assert _table_columns("puzzles") == {
        "date": "TEXT",
        "difficulty": "TEXT",
        "grid": "TEXT",
        "solution": "TEXT",
        "created_at": "TEXT",
    }


def test_puzzles_primary_key():
    assert _primary_key("puzzles") == ["date", "difficulty"]


def test_sessions_table_columns():
    assert _table_columns("sessions") == {
        "wallet": "TEXT",
        "date": "TEXT",
        "difficulty": "TEXT",
        "start_time_utc": "TEXT",
        "attempts": "INTEGER",
        "solved": "INTEGER",
        "solve_time_seconds": "REAL",
        "name": "TEXT",
        "solved_at_utc": "TEXT",
    }


def test_sessions_primary_key():
    assert _primary_key("sessions") == ["wallet", "date", "difficulty"]


def test_leaderboard_index_exists():
    conn = db.get_connection()
    row = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master "
        "WHERE type = 'index' AND name = 'idx_leaderboard'"
    ).fetchone()
    assert row is not None
    assert row["tbl_name"] == "sessions"


# ---------------------------------------------------------------------------
# 3. init_db() idempotency
# ---------------------------------------------------------------------------

def test_init_db_can_be_called_repeatedly():
    # Fixture already called it once; calling again must not raise.
    db.init_db()
    db.init_db()


def test_init_db_does_not_wipe_existing_data():
    date_str = "2026-05-24"
    state.get_or_create_session("0xKeep", date_str, "easy")
    state.record_solve(
        "0xKeep", date_str, "easy",
        "Keeper", 42.0, datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )

    db.init_db()

    session = state.get_session("0xKeep", date_str, "easy")
    assert session is not None
    assert session["solved"] is True
    assert session["name"] == "Keeper"
