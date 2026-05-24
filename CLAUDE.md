# Agentic Sudoku — Project Map

Daily Sudoku game served as paid API endpoints. Agents pay USDC via x402 to fetch a puzzle, submit an answer, and compete on a shared leaderboard.

## Stack

Python 3.12, FastAPI, uvicorn, py-sudoku, x402, Pydantic v2, pytest

Run with: `SKIP_PAYMENT=true python run.py`  
Tests: `SKIP_PAYMENT=true pytest tests/`

---

## App Files (`app/`)

### `app/config.py`
All constants and env vars. `SKIP_PAYMENT` (bool, default false) bypasses x402 in dev/tests. `MERCHANT_WALLET`, `USDC_BASE`, `CDP_FACILITATOR_URL`, `NETWORK`, `GRACE_WINDOW_HOURS`. Other modules access via `from app import config` then `config.X`.

### `app/puzzle.py`
Puzzle generation and token utilities.
- `get_cached_puzzle(date, difficulty)` → `(grid, solution)` — generates a deterministic 9×9 puzzle via py-sudoku seeded from the date, caches in a module-level dict so repeated calls are free. Grid uses 0 for blank cells; solution has no zeros.
- `daily_seed(date, difficulty)` → int seed formula
- `puzzle_token(date, difficulty)` → `"YYYY-MM-DD-easy"` string
- `parse_token(token)` → `(date, difficulty)`, raises `ValueError` on bad input
- `VALID_DIFFICULTIES` = `frozenset({"easy", "hard"})`

### `app/state.py`
All in-memory runtime state (no database).

Two module-level dicts:
- `_sessions`: keyed by `(wallet, date_str, difficulty)` — stores `start_time_utc` (locked on first fetch), `attempts`, `solved`, `solve_time_seconds`, `name`, `solved_at_utc`
- `_leaderboard`: keyed by `(date_str, difficulty)` — list of solve entries sorted by `(solve_time_seconds, solved_at_utc)` ascending

Key behaviors: `get_or_create_session` locks `start_time_utc` on creation and never updates it. `record_solve` is idempotent (no-op if already solved). `clear_state()` resets everything (used in tests).

### `app/grading.py`
Grid validation and coarse correctness reporting.
- `validate_grid_shape(grid)` → error string or None. Submitted grids must be 9×9 with values 1–9 (0 is not valid in submissions).
- `grade_submission(submitted, solution)` → `{correct, rows_correct, cols_correct, boxes_correct}`. Returns row/col/box flags but not per-cell detail (intentional: prevents binary-search probing).

### `app/models.py`
All Pydantic request/response models:
- `SubmitAnswerRequest` — body for submit endpoint; `name` truncated to 8 chars by validator
- `PuzzleResponse` — response for `GET /get_daily_puzzle`
- `SubmitResponseIncorrect` / `SubmitResponseCorrect` — two possible submit responses
- `LeaderboardResponse`, `LeaderboardEntry`, `FirstSolverInfo`, `YouInfo` — leaderboard response pieces

### `app/main.py`
FastAPI app factory and all three route handlers.

`create_app()` builds the app and conditionally attaches x402 middleware (skipped when `SKIP_PAYMENT=true`). Module-level helpers:
- `get_wallet_address(request)` — reads `request.state.payer` (set by x402 in prod) or falls back to `X-Payer-Address` header (tests), 401 if neither
- `_validate_token_window(token, now)` — accepts today's or yesterday's token (within `GRACE_WINDOW_HOURS`), 400 otherwise

Routes:
- `GET /get_daily_puzzle?difficulty=` ($0.03) — returns puzzle grid + locked start time
- `POST /submit_daily_puzzle_answer` ($0.01) — grades submitted 9×9 grid, updates leaderboard on correct solve
- `GET /get_daily_leaderboard?difficulty=&date=` (free) — top 10 solvers, first-solver shoutout, optional `you` field

All date operations use `datetime.now(timezone.utc).date()` throughout to avoid local/UTC mismatch.

`_attach_payment_middleware(app)` — configures x402 with CDP facilitator and Bazaar discovery metadata for the two paid routes.

---

## Entry Point

### `run.py`
`uvicorn.run(create_app(), host="0.0.0.0", port=8000)` — local dev launcher.

---

## Tests (`tests/`)

**Keep this section current.** When adding or removing test files or significantly changing coverage, update the file descriptions and counts here.

### `tests/test_puzzle.py`
19 unit tests for `app/puzzle.py`: deterministic seeding, board normalization, caching, token format/parsing, hard-vs-easy blank count, solution validity (rows/cols/boxes each contain 1–9).

### `tests/test_state.py`
19 unit tests for `app/state.py`: session creation/locking, attempt counting, solve idempotency, leaderboard sort order and tiebreaking, `clear_state`, date/difficulty key isolation.

### `tests/test_grading.py`
15 unit tests for `app/grading.py`: shape validation (including 0-rejection, None, empty list, negative values), row/col/box correctness flags, all-wrong grid, box index layout.

### `tests/test_token_window.py`
10 unit tests for `_validate_token_window` in `app/main.py`: today's token, yesterday within 2h grace, at boundary (rejected), after grace (rejected), future token, old token, invalid format/difficulty.

### `tests/test_api.py`
40 integration tests for all three endpoints via FastAPI `TestClient`. Sets `SKIP_PAYMENT=true` at the top before any imports. Uses `X-Payer-Address` header to inject wallet identity. Uses `_today_utc()` helper everywhere dates are compared. Covers happy paths, missing/invalid fields (422), auth errors (401), bad tokens (400), leaderboard date validation, idempotent double-solve, easy/hard isolation.

---

## Other Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Runtime + dev dependencies |
| `.env.example` | Template: set `MERCHANT_WALLET` and optionally `SKIP_PAYMENT=true` |
| `sudoku_daily_spec.md` | Full product spec: puzzle design, x402 wiring, endpoint schemas |
| `docs/superpowers/plans/2026-05-23-daily-sudoku-api.md` | Original implementation plan |
