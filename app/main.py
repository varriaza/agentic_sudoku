from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request

from app import config, db
from app.grading import grade_submission, validate_grid_shape
from app.models import (
    LeaderboardEntry,
    LeaderboardResponse,
    PuzzleResponse,
    SubmitAnswerRequest,
    SubmitResponseCorrect,
    SubmitResponseIncorrect,
    FirstSolverInfo,
    YouInfo,
)
from app.puzzle import (
    VALID_DIFFICULTIES,
    get_cached_puzzle,
    parse_token,
    puzzle_token,
)
from app import state


def get_wallet_address(request: Request) -> str:
    """Extract wallet address set by x402 middleware, or test header fallback."""
    if hasattr(request.state, "payer") and request.state.payer:
        return request.state.payer
    wallet = request.headers.get("X-Payer-Address")
    if not wallet:
        raise HTTPException(status_code=401, detail="Wallet address not found in payment")
    return wallet


def _validate_token_window(token: str, now: datetime) -> tuple[date, str]:
    """Parse token and check it's for today or yesterday within grace window."""
    try:
        puzzle_date, difficulty = parse_token(token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    today = now.date()
    yesterday = today - timedelta(days=1)

    if puzzle_date == today:
        return puzzle_date, difficulty
    elif puzzle_date == yesterday:
        rollover = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        if now < rollover + timedelta(hours=config.GRACE_WINDOW_HOURS):
            return puzzle_date, difficulty
        raise HTTPException(
            status_code=400,
            detail=f"Yesterday's token expired (grace window is {config.GRACE_WINDOW_HOURS} hours after rollover).",
        )
    else:
        raise HTTPException(status_code=400, detail="Token is too old or from the future.")


def create_app() -> FastAPI:
    # Ensure the SQLite schema exists before any request touches the store.
    db.init_db()
    app = FastAPI(title="Daily Sudoku API")

    if not config.SKIP_PAYMENT:
        _attach_payment_middleware(app)

    @app.get("/get_daily_puzzle", response_model=PuzzleResponse)
    def get_daily_puzzle(
        request: Request,
        difficulty: str = Query(..., description="easy or hard"),
    ):
        if difficulty not in VALID_DIFFICULTIES:
            raise HTTPException(status_code=400, detail=f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}")
        wallet = get_wallet_address(request)
        today = datetime.now(timezone.utc).date()
        grid, _ = get_cached_puzzle(today, difficulty)
        session = state.get_or_create_session(wallet, today.isoformat(), difficulty)
        token = puzzle_token(today, difficulty)
        return PuzzleResponse(
            puzzle_token=token,
            difficulty=difficulty,
            date=today.isoformat(),
            grid=grid,
            start_time_utc=session["start_time_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            notes=(
                "0 = empty cell. Submit your full grid to submit_daily_puzzle_answer "
                "using this puzzle_token. Re-fetching returns the same puzzle and does "
                "not reset your start time."
            ),
        )

    @app.post("/submit_daily_puzzle_answer")
    def submit_daily_puzzle_answer(
        request: Request,
        body: SubmitAnswerRequest,
    ):
        wallet = get_wallet_address(request)
        now = datetime.now(timezone.utc)

        # Validate and parse token
        try:
            puzzle_date, difficulty = _validate_token_window(body.puzzle_token, now)
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Agent must have fetched the puzzle first
        session = state.get_session(wallet, puzzle_date.isoformat(), difficulty)
        if session is None:
            raise HTTPException(
                status_code=400,
                detail="No puzzle session found. Call /get_daily_puzzle first.",
            )

        # Validate submitted grid shape
        error = validate_grid_shape(body.grid)
        if error:
            raise HTTPException(status_code=400, detail=error)

        # Grade against cached solution
        _, solution = get_cached_puzzle(puzzle_date, difficulty)
        grade = grade_submission(body.grid, solution)
        attempts = state.increment_attempts(wallet, puzzle_date.isoformat(), difficulty)
        elapsed = (now - session["start_time_utc"]).total_seconds()

        if not grade["correct"]:
            return SubmitResponseIncorrect(
                rows_correct=grade["rows_correct"],
                cols_correct=grade["cols_correct"],
                boxes_correct=grade["boxes_correct"],
                attempts=attempts,
                elapsed_seconds=elapsed,
                note="Not yet solved. Keep going!",
            )

        # Correct — record to leaderboard (idempotent: won't overwrite first solve)
        state.record_solve(
            wallet, puzzle_date.isoformat(), difficulty,
            body.name, elapsed, now,
        )
        rank = state.get_rank(wallet, puzzle_date.isoformat(), difficulty)
        lb = state.get_leaderboard(puzzle_date.isoformat(), difficulty)
        first_solver_name = lb[0]["name"] if lb else None

        return SubmitResponseCorrect(
            solve_time_seconds=elapsed,
            attempts=attempts,
            rank=rank,
            first_solver_today=first_solver_name,
            note=f"Solved! You are #{rank} on today's {difficulty} leaderboard.",
        )

    @app.get("/get_daily_leaderboard", response_model=LeaderboardResponse)
    def get_daily_leaderboard(
        request: Request,
        difficulty: str = Query("easy", description="easy or hard"),
        date_param: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    ):
        if difficulty not in VALID_DIFFICULTIES:
            raise HTTPException(status_code=400, detail=f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}")

        if date_param is None:
            target_date = datetime.now(timezone.utc).date()
        else:
            try:
                target_date = date.fromisoformat(date_param)
            except ValueError:
                raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
            today = datetime.now(timezone.utc).date()
            yesterday = today - timedelta(days=1)
            if target_date not in (today, yesterday):
                raise HTTPException(status_code=400, detail="date must be today or yesterday")

        date_str = target_date.isoformat()
        lb = state.get_leaderboard(date_str, difficulty)
        top10 = [
            LeaderboardEntry(rank=i + 1, name=e["name"], solve_time_seconds=e["solve_time_seconds"])
            for i, e in enumerate(lb[:10])
        ]
        first_solver = None
        if lb:
            # First solver = earliest solved_at_utc, not necessarily fastest solve time
            first = min(lb, key=lambda e: e["solved_at_utc"])
            first_solver = FirstSolverInfo(
                name=first["name"],
                solved_at_utc=first["solved_at_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

        # Optional wallet for "you" field
        wallet = request.headers.get("X-Payer-Address")
        if not wallet and hasattr(request.state, "payer"):
            wallet = request.state.payer
        you = None
        if wallet:
            session = state.get_session(wallet, date_str, difficulty)
            if session and session["solved"]:
                rank = state.get_rank(wallet, date_str, difficulty)
                you = YouInfo(
                    name=session["name"],
                    rank=rank,
                    solve_time_seconds=session["solve_time_seconds"],
                )

        return LeaderboardResponse(
            date=date_str,
            difficulty=difficulty,
            first_solver_today=first_solver,
            top10=top10,
            you=you,
        )

    return app


def _attach_payment_middleware(app: FastAPI) -> None:
    try:
        from x402.fastapi.middleware import require_payment
        from x402.facilitators import cdp_facilitator
    except ImportError as e:
        raise RuntimeError(
            "x402 package not found or missing expected modules. "
            "Install it and verify import paths match your installed version."
        ) from e

    GET_PUZZLE_EXAMPLE = {
        "puzzle_token": "2026-05-23-hard",
        "difficulty": "hard",
        "date": "2026-05-23",
        "grid": [[5, 3, 0, 0, 7, 0, 0, 0, 0]] * 9,
        "start_time_utc": "2026-05-23T14:02:11Z",
        "notes": "0 = empty cell. Submit the full grid to submit_daily_puzzle_answer using this puzzle_token.",
    }

    app.middleware("http")(
        require_payment(
            facilitator=cdp_facilitator(url=config.CDP_FACILITATOR_URL),
            routes={
                "/get_daily_puzzle": {
                    "price": "$0.03",
                    "network": config.NETWORK,
                    "asset": config.USDC_BASE,
                    "pay_to_address": config.MERCHANT_WALLET,
                    "max_timeout_seconds": 300,
                    "description": (
                        "Fetch today's shared Sudoku puzzle (easy or hard). "
                        "Returns a 9x9 grid (0 = blank), a puzzle_token, and your locked start time."
                    ),
                    "mime_type": "application/json",
                    "extensions": {
                        "bazaar": {
                            "discoverable": True,
                            "inputSchema": {
                                "queryParams": {
                                    "difficulty": {
                                        "type": "string",
                                        "description": "easy or hard",
                                        "required": True,
                                    }
                                }
                            },
                            "outputSchema": {
                                "type": "object",
                                "example": GET_PUZZLE_EXAMPLE,
                            },
                        }
                    },
                },
                "/submit_daily_puzzle_answer": {
                    "price": "$0.01",
                    "network": config.NETWORK,
                    "asset": config.USDC_BASE,
                    "pay_to_address": config.MERCHANT_WALLET,
                    "max_timeout_seconds": 300,
                    "description": (
                        "Submit a completed 9x9 grid for today's puzzle. "
                        "Returns coarse correctness (rows/cols/boxes), and on a full solve "
                        "your rank and solve time."
                    ),
                    "mime_type": "application/json",
                    "extensions": {
                        "bazaar": {
                            "discoverable": True,
                            "inputSchema": {
                                "body": {
                                    "puzzle_token": {"type": "string", "required": True},
                                    "grid": {"type": "array", "required": True},
                                    "name": {"type": "string", "required": True, "maxLength": 8},
                                }
                            },
                            "outputSchema": {"type": "object"},
                        }
                    },
                },
            },
        )
    )
