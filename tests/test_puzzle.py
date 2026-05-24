from datetime import date
from app.puzzle import (
    daily_seed,
    board_to_json,
    get_cached_puzzle,
    puzzle_token,
    parse_token,
    VALID_DIFFICULTIES,
)


def test_daily_seed_is_deterministic():
    d = date(2026, 5, 23)
    assert daily_seed(d, "easy") == daily_seed(d, "easy")
    assert daily_seed(d, "hard") == daily_seed(d, "hard")


def test_daily_seed_differs_by_difficulty():
    d = date(2026, 5, 23)
    assert daily_seed(d, "easy") != daily_seed(d, "hard")


def test_daily_seed_differs_by_date():
    d1 = date(2026, 5, 23)
    d2 = date(2026, 5, 24)
    assert daily_seed(d1, "easy") != daily_seed(d2, "easy")


def test_board_to_json_converts_none_to_zero():
    board = [[1, None, 3], [None, 5, None], [7, 8, 9]]
    result = board_to_json(board)
    assert result == [[1, 0, 3], [0, 5, 0], [7, 8, 9]]


def test_board_to_json_leaves_numbers_unchanged():
    board = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert board_to_json(board) == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]


def test_get_cached_puzzle_returns_9x9_grid():
    d = date(2026, 5, 23)
    grid, solution = get_cached_puzzle(d, "easy")
    assert len(grid) == 9
    assert all(len(row) == 9 for row in grid)
    assert len(solution) == 9
    assert all(len(row) == 9 for row in solution)


def test_get_cached_puzzle_grid_has_blanks():
    d = date(2026, 5, 23)
    grid, _ = get_cached_puzzle(d, "easy")
    zeros = sum(cell == 0 for row in grid for cell in row)
    assert zeros > 0, "Puzzle grid should have blank cells (zeros)"


def test_get_cached_puzzle_solution_has_no_blanks():
    d = date(2026, 5, 23)
    _, solution = get_cached_puzzle(d, "easy")
    zeros = sum(cell == 0 for row in solution for cell in row)
    assert zeros == 0, "Solution grid should have no blank cells"


def test_get_cached_puzzle_is_same_puzzle_every_call():
    d = date(2026, 5, 23)
    grid1, sol1 = get_cached_puzzle(d, "easy")
    grid2, sol2 = get_cached_puzzle(d, "easy")
    assert grid1 == grid2
    assert sol1 == sol2


def test_get_cached_puzzle_differs_by_difficulty():
    d = date(2026, 5, 23)
    easy_grid, _ = get_cached_puzzle(d, "easy")
    hard_grid, _ = get_cached_puzzle(d, "hard")
    assert easy_grid != hard_grid


def test_puzzle_token_format():
    d = date(2026, 5, 23)
    assert puzzle_token(d, "easy") == "2026-05-23-easy"
    assert puzzle_token(d, "hard") == "2026-05-23-hard"


def test_parse_token_valid():
    d, difficulty = parse_token("2026-05-23-easy")
    assert d == date(2026, 5, 23)
    assert difficulty == "easy"


def test_parse_token_hard():
    d, difficulty = parse_token("2026-05-23-hard")
    assert d == date(2026, 5, 23)
    assert difficulty == "hard"


def test_parse_token_invalid_difficulty_raises():
    import pytest
    with pytest.raises(ValueError, match="Invalid difficulty"):
        parse_token("2026-05-23-medium")


def test_parse_token_invalid_format_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_token("not-a-token")


def test_get_cached_puzzle_hard_has_more_blanks_than_easy():
    d = date(2026, 5, 23)
    easy_grid, _ = get_cached_puzzle(d, "easy")
    hard_grid, _ = get_cached_puzzle(d, "hard")
    easy_blanks = sum(cell == 0 for row in easy_grid for cell in row)
    hard_blanks = sum(cell == 0 for row in hard_grid for cell in row)
    assert hard_blanks > easy_blanks


def test_get_cached_puzzle_solution_rows_each_contain_1_through_9():
    d = date(2026, 5, 23)
    _, solution = get_cached_puzzle(d, "easy")
    for row in solution:
        assert sorted(row) == list(range(1, 10))


def test_get_cached_puzzle_solution_cols_each_contain_1_through_9():
    d = date(2026, 5, 23)
    _, solution = get_cached_puzzle(d, "easy")
    for col_idx in range(9):
        col = [solution[r][col_idx] for r in range(9)]
        assert sorted(col) == list(range(1, 10))


def test_get_cached_puzzle_solution_boxes_each_contain_1_through_9():
    d = date(2026, 5, 23)
    _, solution = get_cached_puzzle(d, "easy")
    for box_r in range(3):
        for box_c in range(3):
            box = [
                solution[box_r * 3 + r][box_c * 3 + c]
                for r in range(3)
                for c in range(3)
            ]
            assert sorted(box) == list(range(1, 10))
