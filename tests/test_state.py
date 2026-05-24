from datetime import datetime, timezone, timedelta
import pytest
from app.state import (
    get_or_create_session,
    get_session,
    increment_attempts,
    record_solve,
    get_leaderboard,
    get_rank,
    clear_state,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Clear all in-memory state before each test."""
    clear_state()


def test_get_or_create_session_creates_new():
    session = get_or_create_session("0xABC", "2026-05-23", "easy")
    assert session["wallet"] == "0xABC"
    assert session["date_str"] == "2026-05-23"
    assert session["difficulty"] == "easy"
    assert session["attempts"] == 0
    assert session["solved"] is False
    assert session["start_time_utc"] is not None


def test_get_or_create_session_start_time_locked():
    session1 = get_or_create_session("0xABC", "2026-05-23", "easy")
    t1 = session1["start_time_utc"]
    session2 = get_or_create_session("0xABC", "2026-05-23", "easy")
    assert session2["start_time_utc"] == t1


def test_get_or_create_session_different_wallets():
    s1 = get_or_create_session("0xAAA", "2026-05-23", "easy")
    s2 = get_or_create_session("0xBBB", "2026-05-23", "easy")
    assert s1 is not s2


def test_get_session_returns_none_when_missing():
    assert get_session("0xABC", "2026-05-23", "easy") is None


def test_get_session_returns_session_after_create():
    get_or_create_session("0xABC", "2026-05-23", "easy")
    session = get_session("0xABC", "2026-05-23", "easy")
    assert session is not None
    assert session["wallet"] == "0xABC"


def test_increment_attempts():
    get_or_create_session("0xABC", "2026-05-23", "easy")
    count = increment_attempts("0xABC", "2026-05-23", "easy")
    assert count == 1
    count = increment_attempts("0xABC", "2026-05-23", "easy")
    assert count == 2


def test_record_solve_marks_session_solved():
    get_or_create_session("0xABC", "2026-05-23", "hard")
    solved_at = datetime.now(timezone.utc)
    record_solve("0xABC", "2026-05-23", "hard", "ada_lvl", 63.0, solved_at)
    session = get_session("0xABC", "2026-05-23", "hard")
    assert session["solved"] is True
    assert session["solve_time_seconds"] == 63.0
    assert session["name"] == "ada_lvl"


def test_record_solve_does_not_overwrite_first_solve():
    get_or_create_session("0xABC", "2026-05-23", "hard")
    t1 = datetime.now(timezone.utc)
    record_solve("0xABC", "2026-05-23", "hard", "ada_lvl", 63.0, t1)
    t2 = t1 + timedelta(seconds=10)
    record_solve("0xABC", "2026-05-23", "hard", "ada_lvl", 30.0, t2)  # attempt to improve
    session = get_session("0xABC", "2026-05-23", "hard")
    assert session["solve_time_seconds"] == 63.0  # unchanged


def test_leaderboard_is_empty_before_any_solve():
    lb = get_leaderboard("2026-05-23", "easy")
    assert lb == []


def test_leaderboard_contains_solver_after_record_solve():
    get_or_create_session("0xABC", "2026-05-23", "easy")
    solved_at = datetime.now(timezone.utc)
    record_solve("0xABC", "2026-05-23", "easy", "turing7", 31.0, solved_at)
    lb = get_leaderboard("2026-05-23", "easy")
    assert len(lb) == 1
    assert lb[0]["name"] == "turing7"
    assert lb[0]["solve_time_seconds"] == 31.0


def test_leaderboard_sorted_by_solve_time():
    now = datetime.now(timezone.utc)
    get_or_create_session("0xAAA", "2026-05-23", "easy")
    get_or_create_session("0xBBB", "2026-05-23", "easy")
    record_solve("0xAAA", "2026-05-23", "easy", "slow_bot", 100.0, now)
    record_solve("0xBBB", "2026-05-23", "easy", "fast_bot", 22.0, now + timedelta(seconds=5))
    lb = get_leaderboard("2026-05-23", "easy")
    assert lb[0]["name"] == "fast_bot"
    assert lb[1]["name"] == "slow_bot"


def test_leaderboard_tiebreak_by_solved_at():
    t1 = datetime(2026, 5, 23, 8, 0, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(seconds=30)
    get_or_create_session("0xAAA", "2026-05-23", "easy")
    get_or_create_session("0xBBB", "2026-05-23", "easy")
    record_solve("0xBBB", "2026-05-23", "easy", "late_tie", 22.0, t2)
    record_solve("0xAAA", "2026-05-23", "easy", "early_tie", 22.0, t1)
    lb = get_leaderboard("2026-05-23", "easy")
    assert lb[0]["name"] == "early_tie"


def test_get_rank_returns_correct_position():
    now = datetime.now(timezone.utc)
    for i, wallet in enumerate(["0xAAA", "0xBBB", "0xCCC"]):
        get_or_create_session(wallet, "2026-05-23", "easy")
        record_solve(wallet, "2026-05-23", "easy", f"bot{i}", float(i + 1) * 10, now)
    assert get_rank("0xAAA", "2026-05-23", "easy") == 1
    assert get_rank("0xBBB", "2026-05-23", "easy") == 2
    assert get_rank("0xCCC", "2026-05-23", "easy") == 3


def test_get_rank_returns_none_if_not_solved():
    assert get_rank("0xABC", "2026-05-23", "easy") is None


def test_get_rank_returns_none_for_session_that_exists_but_not_solved():
    get_or_create_session("0xABC", "2026-05-23", "easy")
    assert get_rank("0xABC", "2026-05-23", "easy") is None


def test_clear_state_removes_sessions():
    get_or_create_session("0xABC", "2026-05-23", "easy")
    clear_state()
    assert get_session("0xABC", "2026-05-23", "easy") is None


def test_clear_state_removes_leaderboard():
    now = datetime.now(timezone.utc)
    get_or_create_session("0xABC", "2026-05-23", "easy")
    record_solve("0xABC", "2026-05-23", "easy", "ada", 30.0, now)
    clear_state()
    assert get_leaderboard("2026-05-23", "easy") == []


def test_leaderboard_different_dates_are_isolated():
    now = datetime.now(timezone.utc)
    get_or_create_session("0xABC", "2026-05-23", "easy")
    record_solve("0xABC", "2026-05-23", "easy", "solver", 30.0, now)
    assert get_leaderboard("2026-05-24", "easy") == []


def test_leaderboard_different_difficulties_are_isolated():
    now = datetime.now(timezone.utc)
    get_or_create_session("0xABC", "2026-05-23", "easy")
    record_solve("0xABC", "2026-05-23", "easy", "solver", 30.0, now)
    assert get_leaderboard("2026-05-23", "hard") == []
