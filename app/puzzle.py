"""Puzzle generation, caching, and token utilities.

`get_cached_puzzle` is backed by the `puzzles` SQLite table — repeated calls
read from the DB instead of regenerating, and the cache survives a server
restart. Puzzles are still deterministic from the date seed, so a missing row
is regenerated and persisted on first access.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sudoku import Sudoku

from app import db


DIFFICULTY_FRACTIONS = {
    "easy": 0.40,
    "hard": 0.62,
}
VALID_DIFFICULTIES = frozenset({"easy", "hard"})


def daily_seed(d: date, difficulty: str) -> int:
    base = int(d.strftime("%Y%m%d"))
    return base * 10 + (1 if difficulty == "hard" else 0)


def board_to_json(board) -> list[list[int]]:
    return [[c if c is not None else 0 for c in row] for row in board]


def _generate_puzzle(d: date, difficulty: str) -> tuple[list[list[int]], list[list[int]]]:
    seed = daily_seed(d, difficulty)
    puzzle = Sudoku(3, seed=seed).difficulty(DIFFICULTY_FRACTIONS[difficulty])
    solution = puzzle.solve()
    return board_to_json(puzzle.board), board_to_json(solution.board)


def get_cached_puzzle(d: date, difficulty: str) -> tuple[list[list[int]], list[list[int]]]:
    """Return `(grid, solution)` for the given (date, difficulty).

    Reads from the `puzzles` table; on a cache miss, generates the puzzle,
    stores it, and returns the freshly built pair.
    """
    date_str = d.isoformat()
    conn = db.get_connection()
    row = conn.execute(
        "SELECT grid, solution FROM puzzles WHERE date = ? AND difficulty = ?",
        (date_str, difficulty),
    ).fetchone()
    if row is not None:
        return json.loads(row["grid"]), json.loads(row["solution"])

    grid, solution = _generate_puzzle(d, difficulty)
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO puzzles (date, difficulty, grid, solution, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                date_str,
                difficulty,
                json.dumps(grid),
                json.dumps(solution),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return grid, solution


def puzzle_token(d: date, difficulty: str) -> str:
    return f"{d.isoformat()}-{difficulty}"


def parse_token(token: str) -> tuple[date, str]:
    # Format: "YYYY-MM-DD-easy" or "YYYY-MM-DD-hard"
    # Split on last hyphen to get difficulty
    idx = token.rfind("-")
    if idx == -1:
        raise ValueError(f"Invalid token format: {token}")
    date_str = token[:idx]
    difficulty = token[idx + 1:]
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"Invalid difficulty in token: {difficulty!r}")
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid date in token: {date_str!r}")
    return d, difficulty
