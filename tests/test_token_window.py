import os
os.environ["SKIP_PAYMENT"] = "true"

import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException

from app.main import _validate_token_window


def _dt(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc)


TODAY = date(2026, 5, 23)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
OLD_DATE = date(2026, 5, 20)


def test_today_easy_token_accepted():
    now = _dt(TODAY, 10)
    d, difficulty = _validate_token_window("2026-05-23-easy", now)
    assert d == TODAY
    assert difficulty == "easy"


def test_today_hard_token_accepted():
    now = _dt(TODAY, 14)
    d, difficulty = _validate_token_window("2026-05-23-hard", now)
    assert d == TODAY
    assert difficulty == "hard"


def test_yesterday_token_within_grace_window_accepted():
    # 1 hour after midnight UTC — within the 2-hour grace window
    now = _dt(TODAY, 1)
    d, difficulty = _validate_token_window("2026-05-22-easy", now)
    assert d == YESTERDAY
    assert difficulty == "easy"


def test_yesterday_token_at_grace_boundary_rejected():
    # Exactly 2 hours after midnight — grace window is exclusive (now < rollover + 2h)
    now = _dt(TODAY, 2)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("2026-05-22-easy", now)
    assert exc.value.status_code == 400


def test_yesterday_token_after_grace_expired_rejected():
    # 3 hours after midnight — well past 2-hour grace
    now = _dt(TODAY, 3)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("2026-05-22-easy", now)
    assert exc.value.status_code == 400


def test_future_token_rejected():
    now = _dt(TODAY, 10)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("2026-05-24-easy", now)
    assert exc.value.status_code == 400


def test_old_past_token_rejected():
    # Token from 3 days ago
    now = _dt(TODAY, 10)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("2026-05-20-easy", now)
    assert exc.value.status_code == 400


def test_invalid_token_format_rejected():
    now = _dt(TODAY, 10)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("not-a-valid-token", now)
    assert exc.value.status_code == 400


def test_invalid_difficulty_in_token_rejected():
    now = _dt(TODAY, 10)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window("2026-05-23-medium", now)
    assert exc.value.status_code == 400


def test_yesterday_token_late_evening_before_midnight_rejected():
    # 23:00 on the same day (yesterday's token, but we're still on yesterday) — that's today
    # Actually this case: now is yesterday at 23:00, token is for 2 days ago
    two_days_ago = TODAY - timedelta(days=2)
    now = _dt(YESTERDAY, 23)
    with pytest.raises(HTTPException) as exc:
        _validate_token_window(f"{two_days_ago.isoformat()}-easy", now)
    assert exc.value.status_code == 400
