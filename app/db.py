"""SQLite connection management and schema bootstrap.

One connection per thread is kept in `threading.local()`. FastAPI runs sync
routes on a thread pool — each worker thread reuses its own connection.
WAL mode is enabled so reads don't block on the single writer.

The schema uses `CREATE IF NOT EXISTS`; there is no migration system. Breaking
schema changes during development = delete the `.db` file.
"""

from __future__ import annotations

import sqlite3
import threading

from app import config

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Return this thread's sqlite connection, creating it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        # isolation_level="" (deferred) makes `with conn:` commit/rollback as
        # expected for our short multi-statement updates.
        conn = sqlite3.connect(config.DB_PATH, isolation_level="")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def reset_connection() -> None:
    """Close and clear this thread's connection. Used by tests when the
    `DB_PATH` is repointed at a new temp file between tests."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS puzzles (
                date TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                grid TEXT NOT NULL,
                solution TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (date, difficulty)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                wallet TEXT NOT NULL,
                date TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                start_time_utc TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                solved INTEGER NOT NULL DEFAULT 0,
                solve_time_seconds REAL,
                name TEXT,
                solved_at_utc TEXT,
                PRIMARY KEY (wallet, date, difficulty)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_leaderboard
                ON sessions(date, difficulty, solve_time_seconds, solved_at_utc)
                WHERE solved = 1
            """
        )
