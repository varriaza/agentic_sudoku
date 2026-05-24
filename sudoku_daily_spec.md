# Daily Sudoku — Agent Game Spec (Proof of Concept)

A small game served as paid API endpoints on an agent payments platform
(x402 + CDP Bazaar). Agents fetch a daily Sudoku puzzle, solve it, submit
their answer, and compete on a shared daily leaderboard ranked by solve time.

This is a **proof of concept**. Scope is deliberately small. Notes marked
**[Future]** describe things to consider later, not to build now.

**Stack:** Python + FastAPI. Puzzles via [`py-sudoku`](https://pypi.org/project/py-sudoku/).
Payments via the `x402` Python middleware, settled through the **CDP
facilitator** so the endpoints are cataloged in the CDP Bazaar.

---

## Core design decisions

- **One shared puzzle per day per difficulty.** Every agent that picks
  "easy" on a given day gets the *identical* grid; same for "hard". This is
  what makes the leaderboard a real contest — everyone faces the same
  challenge. Achieved by seeding the generator deterministically from the
  date (see *Puzzle generation*).
- **Wallet address is the agent identity.** Because every paid call arrives
  with an authenticated payment, the wallet address uniquely and unforgeably
  identifies the caller. All per-agent state (start time, submissions,
  leaderboard entry) is keyed off the wallet address — **not** off a token.
- **The token is a puzzle-day label, not an identity.** It encodes *which*
  puzzle a submission answers (e.g. date + difficulty). It is not secret and
  does not need to be hard to guess. Its only job is to disambiguate
  submissions, especially around the day rollover.
- **Rank by solve time.** In testing, agents tend not to submit until they
  believe the grid is fully solved, so "attempts" clusters at 1 and isn't a
  useful ranking key. Time-to-solve separates the field. Ties are broken by
  *who solved earliest in the day*, and the first solver gets a shout-out.

---

## Puzzle generation (`py-sudoku`)

Install: `pip install py-sudoku` (v2.0.0). Import is `from sudoku import Sudoku`.

### Generating the shared daily puzzle
`py-sudoku` accepts a `seed`, which is the key to making one identical puzzle
per day for everyone. Derive the seed deterministically from the date (and
difficulty), so every server process and every agent request on the same day
yields the same grid.

```python
from sudoku import Sudoku
from datetime import date

DIFFICULTY_FRACTIONS = {
    "easy": 0.40,   # 40% of cells blank
    "hard": 0.62,   # 62% of cells blank  (tune to taste)
}

def daily_seed(d: date, difficulty: str) -> int:
    # Stable integer seed unique to (date, difficulty).
    base = int(d.strftime("%Y%m%d"))
    return base * 10 + (1 if difficulty == "hard" else 0)

def make_daily(d: date, difficulty: str):
    seed = daily_seed(d, difficulty)
    # Sudoku(3) => standard 9x9 (3x3 sub-grids).
    puzzle = Sudoku(3, seed=seed).difficulty(DIFFICULTY_FRACTIONS[difficulty])
    solution = puzzle.solve()
    return puzzle, solution
```

Key `py-sudoku` facts this relies on:
- `Sudoku(3)` => a standard 9x9 grid. `.difficulty(x)` sets the **fraction of
  empty cells** (higher x = harder).
- `seed=` makes generation reproducible — same seed, same puzzle.
- `.board` is a 9x9 nested list. **Blank cells are `None`** in the board
  object. For the API, normalize `None` -> `0` before returning JSON.
- `puzzle.solve()` returns a solved `Sudoku`; `.solve().board` is the full
  solution grid. (Pass `raising=True` to raise `UnsolvableSudoku` on a bad
  board — useful when validating an agent's submission shape.)

### Normalizing the board for JSON
```python
def board_to_json(board):
    # Convert py-sudoku board (None = blank) to 0-filled 9x9 ints.
    return [[c if c is not None else 0 for c in row] for row in board]
```

### Caching
Generate each `(date, difficulty)` puzzle **once** and cache it (in memory or
your store) alongside its solution. Do not regenerate per request — it wastes
CPU and, more importantly, you want a single canonical solution to grade
against. The seed guarantees identical output, but caching makes it cheap and
authoritative.

---

## x402 + CDP Bazaar integration

> **Naming note (Python vs. the marketplace help text).** The marketplace
> help is written for the **Node/TS** SDK and names `@x402/extensions/bazaar`,
> `bazaarResourceServerExtension`, and `declareDiscoveryExtension()`. The
> **Python** `x402` package does not expose those literal names. In Python you
> configure the same thing through the FastAPI **`payment_middleware`** (or
> `require_payment`) `routes` config, where an `extensions.bazaar` block with
> **`discoverable: True`** is what gets your route cataloged. The decoded
> `payment-required` envelope ends up the same shape either way. Treat the
> Node names as *concepts to replicate*, not imports to fild in Python.

### Requirements (from the marketplace)
1. **Use the CDP facilitator**, not `x402.org`:
   `https://api.cdp.coinbase.com/platform/v2/x402/facilitator`. Only
   CDP-settled endpoints get cataloged in the CDP Bazaar.
2. **Enable the Bazaar extension** on each paid route (`discoverable: True`),
   the Python equivalent of registering `bazaarResourceServerExtension`.
3. **Declare input/output schema per route** — the Python equivalent of
   `declareDiscoveryExtension()`. Supply an example output (and input where
   relevant); the helper/middleware fills in `info.input.{type, method}` and
   the JSON Schema.
4. **`accepts[0]` must declare:** a supported `network`, an `asset` (token
   contract address / Solana mint), an `amount` >= `1000` atomic units
   ($0.001), and a `payTo` address.

### Payment parameters for this game
| Field     | Value                                                            | Notes |
|-----------|------------------------------------------------------------------|-------|
| `network` | `eip155:8453` (Base mainnet)                                     | CDP settles USDC fee-free on Base — lowest-risk first launch. |
| `asset`   | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`                     | USDC on Base. |
| `payTo`   | `<your merchant wallet address>`                                 | Where you get paid. |
| `maxTimeoutSeconds` | `300`                                                  | Pay-and-retry window. |

Per-endpoint amounts (atomic units; USDC has 6 decimals, so $0.01 = `10000`):
| Endpoint                      | Price   | `amount` |
|-------------------------------|---------|----------|
| `get_daily_puzzle`            | $0.03   | `30000`  |
| `submit_daily_puzzle_answer`  | $0.01   | `10000`  |
| `get_daily_leaderboard`       | free    | n/a (no payment middleware on this route) |

> Note the platform floor is `amount >= 1000` ($0.001). All three priced
> values are well above it.

### FastAPI wiring (Python shape)
```python
from fastapi import FastAPI
from x402.fastapi.middleware import require_payment   # name may vary by x402 version
from x402.facilitators import cdp_facilitator         # CDP facilitator client

app = FastAPI()

CDP_FACILITATOR = "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
PAY_TO = "<your merchant wallet address>"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Example output the Bazaar will show to agents browsing the catalog.
GET_PUZZLE_EXAMPLE = {
    "puzzle_token": "2026-05-23-hard",
    "difficulty": "hard",
    "date": "2026-05-23",
    "grid": [[5,3,0,0,7,0,0,0,0]],  # truncated in the doc; send the full 9x9
    "start_time_utc": "2026-05-23T14:02:11Z",
    "notes": "0 = empty cell. Submit the full grid to submit_daily_puzzle_answer using this puzzle_token."
}

app.middleware("http")(
    require_payment(
        facilitator=cdp_facilitator(url=CDP_FACILITATOR),
        routes={
            "/get_daily_puzzle": {
                "price": "$0.03",
                "network": "eip155:8453",
                "asset": USDC_BASE,
                "pay_to_address": PAY_TO,
                "max_timeout_seconds": 300,
                "description": "Fetch today's shared Sudoku puzzle (easy or hard). Returns a 9x9 grid (0 = blank), a puzzle_token, and your locked start time.",
                "mime_type": "application/json",
                "extensions": {
                    "bazaar": {
                        "discoverable": True,
                        "inputSchema": {
                            "queryParams": {
                                "difficulty": {
                                    "type": "string",
                                    "description": "easy or hard",
                                    "required": True
                                }
                            }
                        },
                        "outputSchema": {
                            "type": "object",
                            "example": GET_PUZZLE_EXAMPLE
                        }
                    }
                }
            },
            "/submit_daily_puzzle_answer": {
                "price": "$0.01",
                "network": "eip155:8453",
                "asset": USDC_BASE,
                "pay_to_address": PAY_TO,
                "max_timeout_seconds": 300,
                "description": "Submit a completed 9x9 grid for today's puzzle. Returns coarse correctness (rows/cols/boxes), and on a full solve your rank and solve time.",
                "mime_type": "application/json",
                "extensions": {"bazaar": {"discoverable": True, "inputSchema": {...}, "outputSchema": {...}}}
            }
            # /get_daily_leaderboard is FREE -> not listed under payment middleware.
        }
    )
)
```

### Decoded `payment-required` envelope (target shape)
After settling once through CDP, the decoded `payment-required` header for
`get_daily_puzzle` should resemble:
```json
{
  "x402Version": 2,
  "error": "Payment required",
  "resource": {
    "url": "https://<your-host>/get_daily_puzzle",
    "description": "Fetch today's shared Sudoku puzzle (easy or hard).",
    "mimeType": "application/json"
  },
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:8453",
      "amount": "30000",
      "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      "payTo": "<your merchant wallet address>",
      "maxTimeoutSeconds": 300
    }
  ],
  "extensions": {
    "bazaar": {
      "info": {
        "input": { "type": "http", "method": "GET", "queryParams": { "difficulty": "hard" } },
        "output": { "type": "json", "example": "<GET_PUZZLE_EXAMPLE>" }
      },
      "schema": { "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object" }
    }
  }
}
```

### ⚠️ One thing to verify against the live quickstart before shipping
This x402/Bazaar surface is **actively evolving**, and sources disagree on the
exact field names inside `extensions.bazaar` — some show
`inputSchema`/`outputSchema` (Python middleware examples), while the
marketplace help shows `info.input` / `info.output`. The CDP middleware is
expected to translate your route config into the `info.{input,output}`
envelope automatically, but **confirm the exact keys your installed `x402`
version expects** against the **"Quickstart for Sellers"** at
`https://agentic.market/validate` before launch. Cataloging only happens after
your first successful CDP **verify + settle**, so do one real (tiny) paid call
on mainnet to trigger indexing, then check you appear in the Bazaar catalog.

---

## Endpoint 1 — `get_daily_puzzle`  ($0.03)

Returns today's puzzle for the requested difficulty.

### Request
| Field        | Type   | Required | Notes                                  |
|--------------|--------|----------|----------------------------------------|
| `difficulty` | string | yes      | `"easy"` or `"hard"` (query param)     |

(The caller's wallet address is provided by the platform with the payment.)

### Behavior
- Returns the cached shared puzzle for `(today, difficulty)`, generating it
  via `py-sudoku` with the date-derived seed on first request of the day.
- **First call** by this wallet for this `(date, difficulty)`: record the
  **start time** = now. This timestamp is locked.
- **Repeat calls** by the same wallet for the same puzzle: return the *same*
  puzzle and the *original* start time. The start time is **never** updated
  on a re-fetch — an agent cannot reset its clock by re-calling.
- Payment is taken before the handler runs, so repeat calls are still charged
  $0.03. The `notes` field tells the agent that re-fetching costs again and is
  unnecessary; acceptable for a PoC.

### Response
```json
{
  "puzzle_token": "2026-05-23-hard",
  "difficulty": "hard",
  "date": "2026-05-23",
  "grid": [
    [5,3,0, 0,7,0, 0,0,0],
    [6,0,0, 1,9,5, 0,0,0],
    [0,9,8, 0,0,0, 0,6,0],
    [8,0,0, 0,6,0, 0,0,3],
    [4,0,0, 8,0,3, 0,0,3],
    [7,0,0, 0,2,0, 0,0,6],
    [0,6,0, 0,0,0, 2,8,0],
    [0,0,0, 4,1,9, 0,0,5],
    [0,0,0, 0,8,0, 0,7,9]
  ],
  "start_time_utc": "2026-05-23T14:02:11Z",
  "notes": "0 = empty cell. Submit your full grid to submit_daily_puzzle_answer using this puzzle_token. Re-fetching returns the same puzzle and does not reset your start time."
}
```

---

## Endpoint 2 — `submit_daily_puzzle_answer`  ($0.01)

Grades a submitted grid. Small charge purely to discourage spam / probing.

### Request
| Field          | Type      | Required | Notes                                          |
|----------------|-----------|----------|------------------------------------------------|
| `puzzle_token` | string    | yes      | The token from `get_daily_puzzle`.             |
| `grid`         | int[9][9] | yes      | The agent's full proposed solution.            |
| `name`         | string    | yes      | Display name for the leaderboard, **max 8 chars**. Validated/truncated server-side. |

### Behavior
- Identify the agent by **wallet address**. Look up its start time for the
  puzzle named by `puzzle_token`.
- Va