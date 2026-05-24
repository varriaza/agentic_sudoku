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
