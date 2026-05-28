#!/usr/bin/env python3
"""End-to-end testnet test: full puzzle flow with real x402 payments on Base Sepolia."""
import asyncio
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import httpx
from dotenv import dotenv_values
from eth_account import Account

# Resolve paths relative to the project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_TESTNET = PROJECT_ROOT / ".env.testnet"
SERVER_PORT = 8099
BASE_URL = f"http://localhost:{SERVER_PORT}"


def load_env() -> dict[str, str]:
    if not ENV_TESTNET.exists():
        print(f"ERROR: {ENV_TESTNET} not found. Run scripts/setup_wallets.py first.")
        sys.exit(1)
    env = dotenv_values(str(ENV_TESTNET))
    for key in ("MERCHANT_WALLET", "USER_WALLET_ADDRESS", "USER_PRIVATE_KEY"):
        if not env.get(key):
            print(f"ERROR: {key} missing from {ENV_TESTNET}")
            sys.exit(1)
    return env


async def wait_for_server(timeout: int = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient() as hc:
                resp = await hc.get(f"{BASE_URL}/get_daily_leaderboard?difficulty=easy")
                if resp.status_code == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Server did not become ready within {timeout}s")


async def fetch_with_payment(
    method: str,
    url: str,
    private_key: str,
    **kwargs,
) -> httpx.Response:
    """Make an HTTP request, automatically paying on 402 response."""
    from x402 import x402Client
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.http import (
        decode_payment_required_header,
        encode_payment_signature_header,
        PAYMENT_REQUIRED_HEADER,
        PAYMENT_SIGNATURE_HEADER,
    )

    account = Account.from_key(private_key)
    client = x402Client()
    register_exact_evm_client(client, account)

    async with httpx.AsyncClient() as hc:
        resp = await hc.request(method, url, **kwargs)
        if resp.status_code != 402:
            return resp

        pr_header = (
            resp.headers.get(PAYMENT_REQUIRED_HEADER.lower())
            or resp.headers.get("payment-required")
        )
        if not pr_header:
            raise ValueError(f"Got 402 but no {PAYMENT_REQUIRED_HEADER} header")

        payment_required = decode_payment_required_header(pr_header)
        payload = await client.create_payment_payload(payment_required)
        payment_header_value = encode_payment_signature_header(payload)

        retry_headers = {
            **kwargs.pop("headers", {}),
            PAYMENT_SIGNATURE_HEADER: payment_header_value,
        }
        return await hc.request(method, url, headers=retry_headers, **kwargs)


async def main() -> None:
    env = load_env()
    merchant_wallet = env["MERCHANT_WALLET"]
    user_address = env["USER_WALLET_ADDRESS"]
    user_private_key = env["USER_PRIVATE_KEY"]

    server_env = {
        **os.environ,
        "TESTNET": "true",
        "SKIP_PAYMENT": "false",
        "MERCHANT_WALLET": merchant_wallet,
        "PORT": str(SERVER_PORT),
    }
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "run.py")],
        env=server_env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    results: dict[str, bool] = {}
    current_step = "unknown"

    try:
        print("Waiting for server to start...")
        await wait_for_server()
        print(f"Server ready on port {SERVER_PORT}.\n")

        today = date.today()

        current_step = "fetch_puzzle"
        # Step 1: Fetch puzzle (pays $0.03 USDC)
        print("Step 1: GET /get_daily_puzzle?difficulty=easy  ($0.03 USDC)...")
        resp = await fetch_with_payment(
            "GET",
            f"{BASE_URL}/get_daily_puzzle?difficulty=easy",
            user_private_key,
        )
        if resp.status_code != 200:
            raise AssertionError(f"Expected 200, got {resp.status_code}: {resp.text[:200]}")
        puzzle_data = resp.json()
        token = puzzle_data["puzzle_token"]
        print(f"  PASS — token={token}")
        results["fetch_puzzle"] = True

        # Resolve today's solution directly from the puzzle module
        from app import db
        from app.puzzle import get_cached_puzzle
        db.init_db()
        _, solution = get_cached_puzzle(today, "easy")

        current_step = "submit_answer"
        # Step 2: Submit answer (pays $0.01 USDC)
        print("Step 2: POST /submit_daily_puzzle_answer  ($0.01 USDC)...")
        resp = await fetch_with_payment(
            "POST",
            f"{BASE_URL}/submit_daily_puzzle_answer",
            user_private_key,
            json={
                "puzzle_token": token,
                "grid": solution,
                "name": "TestBot",
            },
        )
        if resp.status_code != 200:
            raise AssertionError(f"Expected 200, got {resp.status_code}: {resp.text[:200]}")
        result = resp.json()
        if not result.get("correct"):
            raise AssertionError(f"Expected correct=true, got: {result}")
        print(f"  PASS — rank={result.get('rank')}, solve_time={result.get('solve_time_seconds', 0):.1f}s")
        results["submit_answer"] = True

        current_step = "leaderboard"
        # Step 3: Check leaderboard (free)
        print("Step 3: GET /get_daily_leaderboard  (free)...")
        async with httpx.AsyncClient() as hc:
            resp = await hc.get(
                f"{BASE_URL}/get_daily_leaderboard?difficulty=easy",
                headers={"X-Payer-Address": user_address},
            )
        if resp.status_code != 200:
            raise AssertionError(f"Expected 200, got {resp.status_code}: {resp.text[:200]}")
        lb = resp.json()
        names = [e["name"] for e in lb.get("top10", [])]
        if "TestBot" not in names:
            raise AssertionError(f"TestBot not in leaderboard top10: {names}")
        print(f"  PASS — top10 names: {names}")
        results["leaderboard"] = True

    except Exception as exc:
        print(f"\n  FAIL at step '{current_step}': {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n" + "=" * 50)
    for step, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {step}")
    missing = [s for s in ("fetch_puzzle", "submit_answer", "leaderboard") if s not in results]
    for step in missing:
        print(f"  FAIL  {step}  (did not run)")
    all_pass = len(results) == 3 and all(results.values())
    print("=" * 50)
    print(f"Result: {'ALL PASS ✓' if all_pass else 'FAILED ✗'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
