from datetime import date
from sudoku import Sudoku

DIFFICULTY_FRACTIONS = {
    "easy": 0.40,
    "hard": 0.62,
}
VALID_DIFFICULTIES = frozenset({"easy", "hard"})

_puzzle_cache: dict[tuple[str, str], tuple[list, list]] = {}


def daily_seed(d: date, difficulty: str) -> int:
    base = int(d.strftime("%Y%m%d"))
    return base * 10 + (1 if difficulty == "hard" else 0)


def board_to_json(board) -> list[list[int]]:
    return [[c if c is not None else 0 for c in row] for row in board]


def get_cached_puzzle(d: date, difficulty: str) -> tuple[list[list[int]], list[list[int]]]:
    key = (d.isoformat(), difficulty)
    if key not in _puzzle_cache:
        seed = daily_seed(d, difficulty)
        puzzle = Sudoku(3, seed=seed).difficulty(DIFFICULTY_FRACTIONS[difficulty])
        solution = puzzle.solve()
        _puzzle_cache[key] = (board_to_json(puzzle.board), board_to_json(solution.board))
    return _puzzle_cache[key]


def puzzle_token(d: date, difficulty: str) -> str:
    return f"{d.isoformat()}-{difficulty}"


def parse_token(token: str) -> tuple[date, str]:
    # Format: "YYYY-MM-DD-easy" or "YYYY-MM-DD-hard"
    # Split on last hyphen to get difficulty
    idx = token.rfind("-")
    if idx == -1:
        raise ValueError(f"Invalid token format: {token}")
    date_str = token[:idx]
    difficulty = token[idx + 1:]
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"Invalid difficulty in token: {difficulty!r}")
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid date in token: {date_str!r}")
    return d, difficulty
