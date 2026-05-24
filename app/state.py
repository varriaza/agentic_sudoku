from datetime import datetime, timezone
from typing import Optional

_sessions: dict[tuple[str, str, str], dict] = {}
_leaderboard: dict[tuple[str, str], list[dict]] = {}


def clear_state() -> None:
    _sessions.clear()
    _leaderboard.clear()


def get_or_create_session(wallet: str, date_str: str, difficulty: str) -> dict:
    key = (wallet, date_str, difficulty)
    if key not in _sessions:
        _sessions[key] = {
            "wallet": wallet,
            "date_str": date_str,
            "difficulty": difficulty,
            "start_time_utc": datetime.now(timezone.utc),
            "attempts": 0,
            "solved": False,
            "solve_time_seconds": None,
            "name": None,
            "solved_at_utc": None,
        }
    return _sessions[key]


def get_session(wallet: str, date_str: str, difficulty: str) -> Optional[dict]:
    return _sessions.get((wallet, date_str, difficulty))


def increment_attempts(wallet: str, date_str: str, difficulty: str) -> int:
    _sessions[(wallet, date_str, difficulty)]["attempts"] += 1
    return _sessions[(wallet, date_str, difficulty)]["attempts"]


def record_solve(
    wallet: str,
    date_str: str,
    difficulty: str,
    name: str,
    solve_time_seconds: float,
    solved_at: datetime,
) -> None:
    session = _sessions[(wallet, date_str, difficulty)]
    if session["solved"]:
        return
    session["solved"] = True
    session["solve_time_seconds"] = solve_time_seconds
    session["name"] = name
    session["solved_at_utc"] = solved_at

    lb_key = (date_str, difficulty)
    if lb_key not in _leaderboard:
        _leaderboard[lb_key] = []
    _leaderboard[lb_key].append({
        "wallet": wallet,
        "name": name,
        "solve_time_seconds": solve_time_seconds,
        "solved_at_utc": solved_at,
    })
    _leaderboard[lb_key].sort(
        key=lambda e: (round(e["solve_time_seconds"]), e["solved_at_utc"])
    )


def get_leaderboard(date_str: str, difficulty: str) -> list[dict]:
    return _leaderboard.get((date_str, difficulty), [])


def get_rank(wallet: str, date_str: str, difficulty: str) -> Optional[int]:
    for i, entry in enumerate(get_leaderboard(date_str, difficulty), 1):
        if entry["wallet"] == wallet:
            return i
    return None
