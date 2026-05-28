# Dev Wallet Setup — Design

**Date:** 2026-05-28  
**Branch:** feature/as/setup-dev-wallet-for-hko  
**Status:** Approved

## Goal

Set up two wallets on Base Sepolia testnet (merchant + user), fund them with testnet ETH and USDC, fix the x402 v2 import paths in the app, and produce an end-to-end test script that walks through the full puzzle flow with real on-chain payments.

---

## Components

### 1. `scripts/setup_wallets.py` — one-time setup

Creates both wallets and funds them with testnet ETH.

- **Merchant wallet**: CDP-managed server account named `"sudoku-merchant"`. Private key stays in CDP's TEE; only the address is written to disk. Idempotent — if the account already exists, reuses it.
- **User wallet**: Local key pair generated via `eth_account.Account.create()`. Private key written to `.env.testnet` (testnet-only, never committed).
- Calls `cdp.evm.request_faucet(address, network="base-sepolia", token="eth")` on both addresses. If faucet is rate-limited, prints a warning and continues.
- Writes `.env.testnet` (prompts before overwriting if it already exists).
- Prints a checklist reminding the user to fund both addresses with USDC at faucet.circle.com.

**Reads from environment (not written to `.env.testnet`):**
```
CDP_API_KEY_ID
CDP_API_KEY_SECRET
CDP_WALLET_SECRET
```

### 2. `.env.testnet` — output artifact, gitignored

```
MERCHANT_WALLET=0x...
USER_WALLET_ADDRESS=0x...
USER_PRIVATE_KEY=0x...
```

`.gitignore` must include `.env.testnet`.

### 3. `app/config.py` — testnet mode

Add a `TESTNET` env var. When `true`, override network and USDC address:

```python
TESTNET: bool = os.getenv("TESTNET", "false").lower() == "true"

NETWORK = "eip155:84532" if TESTNET else "eip155:8453"
USDC_BASE = (
    "0x036CbD53842c5426634e7929541eC2318f3dCF7e" if TESTNET
    else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
```

Mainnet values are unchanged when `TESTNET` is not set.

### 4. `app/main.py` — fix x402 import paths

The installed x402 v2.11.0 has a different module layout. `_attach_payment_middleware` is updated (~15 lines):

| Old import (broken) | New import (v2.11.0) |
|---|---|
| `from x402.fastapi.middleware import require_payment` | `from x402.http.middleware.fastapi import X402Middleware` |
| `from x402.facilitators import cdp_facilitator` | `from x402.http.facilitator_client import HTTPFacilitatorClient` + `FacilitatorConfig` |
| `app.middleware("http")(require_payment(...))` | `app.add_middleware(X402Middleware, ...)` |

This fix is required for any live payment flow (testnet or mainnet). Existing tests using `SKIP_PAYMENT=true` are unaffected.

### 5. `scripts/test_testnet.py` — end-to-end test script

Full flow with real x402 payments:

```
1. Load .env.testnet → MERCHANT_WALLET, USER_WALLET_ADDRESS, USER_PRIVATE_KEY
2. Start server subprocess: TESTNET=true SKIP_PAYMENT=false MERCHANT_WALLET=... python run.py
3. Poll GET /get_daily_leaderboard until server is ready (10s timeout)
4. Build x402 client with USER_PRIVATE_KEY (signs EIP-3009 payment proofs)
5. GET /get_daily_puzzle?difficulty=easy   → pay $0.03 USDC → assert 200, capture grid + token
6. Solve puzzle (call get_cached_puzzle() directly — same seed → known solution)
7. POST /submit_daily_puzzle_answer        → pay $0.01 USDC → assert correct=true, rank >= 1
8. GET /get_daily_leaderboard              → free → assert user wallet appears in top10
9. Kill server subprocess
10. Print summary: steps passed/failed, USDC spent, tx hashes
```

The test script does **not** need CDP credentials — it only uses the local user private key.

---

## Environment Variables Summary

| Var | Set by | Used by |
|---|---|---|
| `CDP_API_KEY_ID` | User (shell/`.env`) | `setup_wallets.py` |
| `CDP_API_KEY_SECRET` | User (shell/`.env`) | `setup_wallets.py` |
| `CDP_WALLET_SECRET` | User (shell/`.env`) | `setup_wallets.py` |
| `MERCHANT_WALLET` | `.env.testnet` output | Server, `test_testnet.py` |
| `USER_WALLET_ADDRESS` | `.env.testnet` output | `test_testnet.py` (info only) |
| `USER_PRIVATE_KEY` | `.env.testnet` output | `test_testnet.py` |
| `TESTNET` | Shell when running server | `app/config.py` |
| `SKIP_PAYMENT` | Shell when running server | `app/main.py` |

---

## Out of Scope

- Mainnet deployment or production `.env` changes
- Modifying existing pytest tests (they continue to use `SKIP_PAYMENT=true`)
- Adding `TESTNET` to `.env.example` (that is the human configuration task)

---

## Run Order

```bash
# 1. Set CDP credentials in shell
export CDP_API_KEY_ID=...
export CDP_API_KEY_SECRET=...
export CDP_WALLET_SECRET=...

# 2. Create and fund wallets (ETH only — automated)
python3 scripts/setup_wallets.py

# 3. Fund both wallets with USDC at https://faucet.circle.com (manual)

# 4. Human task: configure .env with MERCHANT_WALLET from .env.testnet

# 5. Run end-to-end testnet test
python3 scripts/test_testnet.py
```
