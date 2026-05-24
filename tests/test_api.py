import os
os.environ["SKIP_PAYMENT"] = "true"  # must be set before importing app

import pytest
from datetime import date
from fastapi.testclient import TestClient
from app.main import create_app
from app import state as state_module

TEST_WALLET = "0xTestWallet0000000000000000000000000001"
TEST_WALLET_2 = "0xTestWallet0000000000000000000000000002"


@pytest.fixture(autouse=True)
def reset_state():
    state_module.clear_state()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def wallet_headers(wallet: str = TEST_WALLET) -> dict:
    return {"X-Payer-Address": wallet}


# --- GET /get_daily_puzzle ---

def test_get_daily_puzzle_returns_200(client):
    resp = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    assert resp.status_code == 200


def test_get_daily_puzzle_response_shape(client):
    resp = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    data = resp.json()
    assert "puzzle_token" in data
    assert "difficulty" in data
    assert "date" in data
    assert "grid" in data
    assert "start_time_utc" in data
    assert "notes" in data


def test_get_daily_puzzle_grid_is_9x9(client):
    resp = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    grid = resp.json()["grid"]
    assert len(grid) == 9
    assert all(len(row) == 9 for row in grid)


def test_get_daily_puzzle_grid_has_zeros(client):
    resp = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    grid = resp.json()["grid"]
    zeros = sum(c == 0 for row in grid for c in row)
    assert zeros > 0


def test_get_daily_puzzle_token_format(client):
    resp = client.get("/get_daily_puzzle?difficulty=hard", headers=wallet_headers())
    token = resp.json()["puzzle_token"]
    assert token.endswith("-hard")
    assert len(token) == len("2026-05-23-hard")


def test_get_daily_puzzle_hard_differs_from_easy(client):
    easy = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    hard = client.get("/get_daily_puzzle?difficulty=hard", headers=wallet_headers())
    assert easy.json()["grid"] != hard.json()["grid"]


def test_get_daily_puzzle_second_call_returns_same_start_time(client):
    r1 = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    t1 = r1.json()["start_time_utc"]
    r2 = client.get("/get_daily_puzzle?difficulty=easy", headers=wallet_headers())
    t2 = r2.json()["start_time_utc"]
    assert t1 == t2


def test_get_daily_puzzle_missing_difficulty_returns_422(client):
    resp = client.get("/get_daily_puzzle", headers=wallet_headers())
    assert resp.status_code == 422


def test_get_daily_puzzle_invalid_difficulty_returns_400(client):
    resp = client.get("/get_daily_puzzle?difficulty=medium", headers=wallet_headers())
    assert resp.status_code == 400


def test_get_daily_puzzle_missing_wallet_returns_401(client):
    resp = client.get("/get_daily_puzzle?difficulty=easy")
    assert resp.status_code == 401


# --- POST /submit_daily_puzzle_answer ---

def _get_puzzle_token(client, difficulty="easy", wallet=TEST_WALLET):
    resp = client.get(f"/get_daily_puzzle?difficulty={difficulty}", headers=wallet_headers(wallet))
    return resp.json()["puzzle_token"]


def _get_correct_solution(difficulty="easy"):
    from app.puzzle import get_cached_puzzle
    _, solution = get_cached_puzzle(date.today(), difficulty)
    return solution


def test_submit_wrong_grid_returns_correct_false(client):
    token = _get_puzzle_token(client, "easy")
    # Submit a grid that is all 1s (definitely wrong)
    bad_grid = [[1] * 9 for _ in range(9)]
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": bad_grid, "name": "testbot"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is False
    assert "rows_correct" in data
    assert "cols_correct" in data
    assert "boxes_correct" in data
    assert data["attempts"] == 1
    assert data["rank"] is None


def test_submit_correct_grid_returns_correct_true(client):
    token = _get_puzzle_token(client, "easy")
    solution = _get_correct_solution("easy")
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": solution, "name": "testbot"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is True
    assert "solve_time_seconds" in data
    assert data["rank"] == 1
    assert "note" in data


def test_submit_increments_attempts(client):
    token = _get_puzzle_token(client, "easy")
    bad_grid = [[1] * 9 for _ in range(9)]
    for i in range(1, 4):
        resp = client.post(
            "/submit_daily_puzzle_answer",
            json={"puzzle_token": token, "grid": bad_grid, "name": "testbot"},
            headers=wallet_headers(),
        )
        assert resp.json()["attempts"] == i


def test_submit_rank_reflects_leaderboard_order(client):
    # TEST_WALLET_2 fetches first -> has larger elapsed -> ranks #2 (slower)
    token2 = _get_puzzle_token(client, "easy", TEST_WALLET_2)
    # TEST_WALLET fetches second -> has smaller elapsed -> ranks #1 (faster)
    token1 = _get_puzzle_token(client, "easy", TEST_WALLET)
    solution = _get_correct_solution("easy")

    # First solver to submit (TEST_WALLET, started later = faster elapsed)
    r1 = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token1, "grid": solution, "name": "first"},
        headers=wallet_headers(TEST_WALLET),
    )
    assert r1.json()["rank"] == 1

    # Second solver to submit (TEST_WALLET_2, started earlier = slower elapsed)
    r2 = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token2, "grid": solution, "name": "second"},
        headers=wallet_headers(TEST_WALLET_2),
    )
    assert r2.json()["rank"] == 2


def test_submit_invalid_grid_shape_returns_400(client):
    token = _get_puzzle_token(client, "easy")
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": [[1] * 9 for _ in range(8)], "name": "bot"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 400


def test_submit_invalid_grid_values_returns_400(client):
    token = _get_puzzle_token(client, "easy")
    bad_grid = [[0] * 9 for _ in range(9)]  # 0s not valid for submission
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": bad_grid, "name": "bot"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 400


def test_submit_unknown_token_returns_400(client):
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": "1999-01-01-easy", "grid": [[1]*9]*9, "name": "bot"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 400


def test_submit_without_fetching_first_returns_400(client):
    # Agent submits without ever calling get_daily_puzzle first
    today_token = f"{date.today().isoformat()}-easy"
    solution = _get_correct_solution("easy")
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": today_token, "grid": solution, "name": "sneaky"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 400


def test_submit_name_truncated_to_8_chars(client):
    token = _get_puzzle_token(client, "easy")
    solution = _get_correct_solution("easy")
    resp = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": solution, "name": "averylongname"},
        headers=wallet_headers(),
    )
    assert resp.status_code == 200
    # Check leaderboard entry has truncated name
    lb = state_module.get_leaderboard(date.today().isoformat(), "easy")
    assert len(lb[0]["name"]) <= 8


def test_submit_first_solver_shoutout(client):
    token = _get_puzzle_token(client, "easy")
    solution = _get_correct_solution("easy")
    r1 = client.post(
        "/submit_daily_puzzle_answer",
        json={"puzzle_token": token, "grid": solution, "name": "champ"},
        headers=wallet_headers(),
    )
    assert r1.json()["first_solver_today"] == "champ"
