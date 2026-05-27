"""Runtime state for sessions and the derived leaderboard.

Backed by SQLite (see `app/db.py`). Public API is identical to the previous
in-memory implementation — callers still pass plain strings and receive dicts
with `datetime` objects for the timestamp fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app import db


_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    # `datetime.fromisoformat` handles offsets natively. Stored values always
    # include a +00:00 (UTC) offset because we serialize timezone-aware values.
    return datetime.fromisoformat(value)


def _row_to_session(row) -> dict:
    return {
        "wallet": row["wallet"],
        "date_str": row["date"],
        "difficulty": row["difficulty"],
        "start_time_utc": _parse_iso(row["start_time_utc"]),
        "attempts": row["attempts"],
        "solved": bool(row["solved"]),
        "solve_time_seconds": row["solve_time_seconds"],
        "name": row["name"],
        "solved_at_utc": _parse_iso(row["solved_at_utc"]),
    }


def clear_state() -> None:
    """Wipe all session and puzzle rows. Used by tests."""
    conn = db.get_connection()
    with conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM puzzles")


def get_or_create_session(wallet: str, date_str: str, difficulty: str) -> dict:
    """Fetch a session or create it. `start_time_utc` is locked on creation
    and never updated by subsequent calls."""
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM sessions WHERE wallet = ? AND date = ? AND difficulty = ?",
        (wallet, date_str, difficulty),
    ).fetchone()
    if row is not None:
        return _row_to_session(row)

    start_time_iso = _utcnow_iso()
    with conn:
        # INSERT OR IGNORE guards against a (rare) race where another thread
        # inserted between our SELECT and INSERT. Re-read either way.
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (wallet, date, difficulty, start_time_utc, attempts, solved)
            VALUES (?, ?, ?, ?, 0, 0)
            """,
            (wallet, date_str, difficulty, start_time_iso),
        )
    row = conn.execute(
        "SELECT * FROM sessions WHERE wallet = ? AND date = ? AND difficulty = ?",
        (wallet, date_str, difficulty),
    ).fetchone()
    return _row_to_session(row)


def get_session(wallet: str, date_str: str, difficulty: str) -> Optional[dict]:
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM sessions WHERE wallet = ? AND date = ? AND difficulty = ?",
        (wallet, date_str, difficulty),
    ).fetchone()
    return _row_to_session(row) if row is not None else None


def increment_attempts(wallet: str, date_str: str, difficulty: str) -> int:
    conn = db.get_connection()
    with conn:
        conn.execute(
            """
            UPDATE sessions
               SET attempts = attempts + 1
             WHERE wallet = ? AND date = ? AND difficulty = ?
            """,
            (wallet, date_str, difficulty),
        )
    row = conn.execute(
        "SELECT attempts FROM sessions WHERE wallet = ? AND date = ? AND difficulty = ?",
        (wallet, date_str, difficulty),
    ).fetchone()
    return row["attempts"]


def record_solve(
    wallet: str,
    date_str: str,
    difficulty: str,
    name: str,
    solve_time_seconds: float,
    solved_at: datetime,
) -> None:
    """Mark a session solved. Idempotent — repeat calls are silently dropped
    so the first solve time and name are preserved."""
    conn = db.get_connection()
    with conn:
        conn.execute(
            """
            UPDATE sessions
               SET solved = 1,
                   solve_time_seconds = ?,
                   name = ?,
                   solved_at_utc = ?
             WHERE wallet = ? AND date = ? AND difficulty = ?
               AND solved = 0
            """,
            (
                solve_time_seconds,
                name,
                solved_at.isoformat(),
                wallet,
                date_str,
                difficulty,
            ),
        )


def get_leaderboard(date_str: str, difficulty: str) -> list[dict]:
    """Return solved sessions for (date, difficulty) ordered by solve time
    then solved-at tiebreaker. Includes the wallet so callers can find
    individual ranks."""
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT wallet, name, solve_time_seconds, solved_at_utc
          FROM sessions
         WHERE date = ? AND difficulty = ? AND solved = 1
         ORDER BY solve_time_seconds ASC, solved_at_utc ASC
        """,
        (date_str, difficulty),
    ).fetchall()
    return [
        {
            "wallet": r["wallet"],
            "name": r["name"],
            "solve_time_seconds": r["solve_time_seconds"],
            "solved_at_utc": _parse_iso(r["solved_at_utc"]),
        }
        for r in rows
    ]


def get_rank(wallet: str, date_str: str, difficulty: str) -> Optional[int]:
    for i, entry in enumerate(get_leaderboard(date_str, difficulty), 1):
        if entry["wallet"] == wallet:
            return i
    return None
