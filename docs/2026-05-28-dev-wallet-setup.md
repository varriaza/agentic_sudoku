# Dev Wallet Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up merchant and user wallets on Base Sepolia, fix the x402 v2 middleware, and produce a working end-to-end testnet test script.

**Architecture:** Four sequential changes: (1) config/gitignore for testnet mode, (2) x402 v2.11.0 middleware fix in app/main.py, (3) one-time setup script using CDP SDK + eth_account, (4) end-to-end test script that spins up the server and makes real on-chain payments.

**Tech Stack:** Python 3.12, cdp-sdk 1.46.0, eth_account (from web3), x402 2.11.0, httpx, FastAPI/uvicorn

---

### Task 1: Gitignore, config, requirements, run.py

**Files:**
- Modify: `.gitignore`
- Modify: `app/config.py`
- Modify: `requirements.txt`
- Modify: `run.py`

- [ ] **Step 1: Add `.env.testnet` to `.gitignore`**

Open `.gitignore` and add this line after the existing `.env` entry:

```
.env.testnet
```

The `.gitignore` block around `.env` should now read:
```
.env
.env.testnet
```

- [ ] **Step 2: Add TESTNET flag to `app/config.py`**

Replace the current `USDC_BASE` and `NETWORK` lines in `app/config.py` with testnet-conditional versions:

Current `app/config.py` (lines 6–12):
```python
MERCHANT_WALLET: str = os.getenv("MERCHANT_WALLET", "0x0000000000000000000000000000000000000000")
SKIP_PAYMENT: bool = os.getenv("SKIP_PAYMENT", "false").lower() == "true"

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
NETWORK = "eip155:8453"
GRACE_WINDOW_HOURS = 2
```

Replace with:
```python
MERCHANT_WALLET: str = os.getenv("MERCHANT_WALLET", "0x0000000000000000000000000000000000000000")
SKIP_PAYMENT: bool = os.getenv("SKIP_PAYMENT", "false").lower() == "true"
TESTNET: bool = os.getenv("TESTNET", "false").lower() == "true"

USDC_BASE = (
    "0x036CbD53842c5426634e7929541eC2318f3dCF7e" if TESTNET
    else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
NETWORK = "eip155:84532" if TESTNET else "eip155:8453"
GRACE_WINDOW_HOURS = 2
```

- [ ] **Step 3: Add cdp-sdk to `requirements.txt`**

Append to `requirements.txt`:
```
cdp-sdk>=1.46.0
```

- [ ] **Step 4: Make `run.py` read PORT from env**

Replace `run.py` with:
```python
import os
import uvicorn
from app.main import create_app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 5: Install cdp-sdk into the venv and run tests**

```bash
.venv/bin/pip install cdp-sdk>=1.46.0
SKIP_PAYMENT=true .venv/bin/pytest tests/ -q
```

Expected: `113 passed`

- [ ] **Step 6: Commit**

```bash
git add .gitignore app/config.py requirements.txt run.py
git commit -m "feat: add TESTNET mode flag and PORT env support"
```

---

### Task 2: Fix x402 v2.11.0 middleware in `app/main.py`

**Files:**
- Modify: `app/main.py`

The installed x402 2.11.0 has a different module layout from the old code. This task rewrites `_attach_payment_middleware` and updates `get_wallet_address` to match the new API.

**Key changes:**
- Old: `from x402.fastapi.middleware import require_payment` → New: `from x402.http.middleware.fastapi import payment_middleware`
- Old: `from x402.facilitators import cdp_facilitator` → New: `from x402.http import HTTPFacilitatorClient, FacilitatorConfig`
- Old: `request.state.payer` → New: `request.state.payment_payload.payload["authorization"]["from"]`

- [ ] **Step 1: Update `get_wallet_address` in `app/main.py`**

Replace the current `get_wallet_address` function (lines 27–34):

```python
def get_wallet_address(request: Request) -> str:
    """Extract wallet address set by x402 middleware, or test header fallback."""
    if hasattr(request.state, "payer") and request.state.payer:
        return request.state.payer
    wallet = request.headers.get("X-Payer-Address")
    if not wallet:
        raise HTTPException(status_code=401, detail="Wallet address not found in payment")
    return wallet
```

With:
```python
def get_wallet_address(request: Request) -> str:
    """Extract wallet address from x402 payment payload, or test header fallback."""
    if hasattr(request.state, "payment_payload") and request.state.payment_payload:
        auth = request.state.payment_payload.payload.get("authorization", {})
        payer = auth.get("from")
        if payer:
            return payer
    wallet = request.headers.get("X-Payer-Address")
    if not wallet:
        raise HTTPException(status_code=401, detail="Wallet address not found in payment")
    return wallet
```

- [ ] **Step 2: Rewrite `_attach_payment_middleware` in `app/main.py`**

Replace the entire `_attach_payment_middleware` function (lines 218–299) with:

```python
def _attach_payment_middleware(app: FastAPI) -> None:
    try:
        from x402 import x402ResourceServer
        from x402.http import HTTPFacilitatorClient, FacilitatorConfig
        from x402.http.middleware.fastapi import payment_middleware
        from x402.mechanisms.evm.exact import register_exact_evm_server
    except ImportError as e:
        raise RuntimeError(
            "x402 package not found or missing expected modules. "
            "Install it and verify import paths match your installed version."
        ) from e

    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=config.CDP_FACILITATOR_URL))
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server)

    routes = {
        "GET /get_daily_puzzle": {
            "accepts": {
                "scheme": "exact",
                "pay_to": config.MERCHANT_WALLET,
                "price": "$0.03",
                "network": config.NETWORK,
                "max_timeout_seconds": 300,
            },
            "description": (
                "Fetch today's shared Sudoku puzzle (easy or hard). "
                "Returns a 9x9 grid (0 = blank), a puzzle_token, and your locked start time."
            ),
            "mime_type": "application/json",
        },
        "POST /submit_daily_puzzle_answer": {
            "accepts": {
                "scheme": "exact",
                "pay_to": config.MERCHANT_WALLET,
                "price": "$0.01",
                "network": config.NETWORK,
                "max_timeout_seconds": 300,
            },
            "description": (
                "Submit a completed 9x9 grid for today's puzzle. "
                "Returns coarse correctness (rows/cols/boxes), and on a full solve "
                "your rank and solve time."
            ),
            "mime_type": "application/json",
        },
    }

    _mw = payment_middleware(routes, server)

    @app.middleware("http")
    async def x402_mw(request, call_next):
        return await _mw(request, call_next)
```

- [ ] **Step 3: Run existing tests**

```bash
SKIP_PAYMENT=true .venv/bin/pytest tests/ -q
```

Expected: `113 passed` — existing tests use `SKIP_PAYMENT=true` so the middleware is never entered.

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "fix: update x402 middleware to v2.11.0 API"
```

---

### Task 3: Create `scripts/setup_wallets.py` and `scripts/__init__.py`

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/setup_wallets.py`

- [ ] **Step 1: Create `scripts/__init__.py`**

Create an empty file at `scripts/__init__.py`:
```python
```
(empty file)

- [ ] **Step 2: Create `scripts/setup_wallets.py`**

Create `scripts/setup_wallets.py` with the following content:

```python
#!/usr/bin/env python3
"""One-time setup: create merchant and user wallets on Base Sepolia, fund with ETH."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account

load_dotenv()

ENV_TESTNET = Path(".env.testnet")
FAUCET_NETWORK = "base-sepolia"
FAUCET_TOKEN = "eth"
MERCHANT_ACCOUNT_NAME = "sudoku-merchant"


async def main() -> None:
    for var in ("CDP_API_KEY_ID", "CDP_API_KEY_SECRET", "CDP_WALLET_SECRET"):
        if not os.environ.get(var):
            print(f"ERROR: {var} is not set. Export it before running this script.")
            sys.exit(1)

    if ENV_TESTNET.exists():
        answer = input(f"{ENV_TESTNET} already exists. Overwrite? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    from cdp import CdpClient

    async with CdpClient() as cdp:
        print(f"Creating/fetching CDP account '{MERCHANT_ACCOUNT_NAME}'...")
        merchant = await cdp.evm.get_or_create_account(MERCHANT_ACCOUNT_NAME)
        print(f"  Merchant address: {merchant.address}")

        print("  Requesting testnet ETH for merchant...")
        try:
            tx = await cdp.evm.request_faucet(merchant.address, FAUCET_NETWORK, FAUCET_TOKEN)
            print(f"  ETH faucet tx: {tx}")
        except Exception as e:
            print(f"  WARNING: ETH faucet failed for merchant: {e}")

        print("Generating local user key pair...")
        user_account = Account.create()
        print(f"  User address: {user_account.address}")

        print("  Requesting testnet ETH for user...")
        try:
            tx = await cdp.evm.request_faucet(user_account.address, FAUCET_NETWORK, FAUCET_TOKEN)
            print(f"  ETH faucet tx: {tx}")
        except Exception as e:
            print(f"  WARNING: ETH faucet failed for user: {e}")

    ENV_TESTNET.write_text(
        f"MERCHANT_WALLET={merchant.address}\n"
        f"USER_WALLET_ADDRESS={user_account.address}\n"
        f"USER_PRIVATE_KEY={user_account.key.hex()}\n"
    )
    print(f"\n.env.testnet written to {ENV_TESTNET.resolve()}")

    print("\n" + "=" * 60)
    print("NEXT STEP: Fund both wallets with USDC on Base Sepolia.")
    print("Go to: https://faucet.circle.com")
    print("Select network: Base Sepolia, token: USDC")
    print(f"  Merchant: {merchant.address}")
    print(f"  User:     {user_account.address}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Run a dry import check**

```bash
SKIP_PAYMENT=true .venv/bin/python -c "import scripts.setup_wallets; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 4: Run existing tests to confirm no regression**

```bash
SKIP_PAYMENT=true .venv/bin/pytest tests/ -q
```

Expected: `113 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/setup_wallets.py
git commit -m "feat: add setup_wallets script for Base Sepolia testnet wallets"
```

---

### Task 4: Create `scripts/test_testnet.py`

**Files:**
- Create: `scripts/test_testnet.py`

- [ ] **Step 1: Create `scripts/test_testnet.py`**

Create `scripts/test_testnet.py`:

```python
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

    try:
        print("Waiting for server to start...")
        await wait_for_server()
        print(f"Server ready on port {SERVER_PORT}.\n")

        today = date.today()

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
        step = next((s for s, ok in results.items() if not ok), "unknown")
        print(f"\n  FAIL at step '{step}': {exc}")
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
```

- [ ] **Step 2: Run a dry import check**

```bash
SKIP_PAYMENT=true .venv/bin/python -c "import scripts.test_testnet; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: Run existing tests to confirm no regression**

```bash
SKIP_PAYMENT=true .venv/bin/pytest tests/ -q
```

Expected: `113 passed`

- [ ] **Step 4: Commit**

```bash
git add scripts/test_testnet.py
git commit -m "feat: add end-to-end testnet test script"
```

---

## Run Order (after plan is implemented)

```bash
# 1. Set CDP credentials
export CDP_API_KEY_ID=...
export CDP_API_KEY_SECRET=...
export CDP_WALLET_SECRET=...

# 2. Create wallets and fund with testnet ETH
python3 scripts/setup_wallets.py

# 3. Fund both addresses with USDC at https://faucet.circle.com
#    (printed by setup_wallets.py)

# 4. Human task: copy MERCHANT_WALLET from .env.testnet into .env

# 5. Run end-to-end testnet test
python3 scripts/test_testnet.py
```
