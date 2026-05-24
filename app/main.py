from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request

from app import config
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
        today = date.today()
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
