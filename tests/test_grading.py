import pytest
from app.grading import validate_grid_shape, grade_submission


VALID_SOLUTION = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2],
    [6, 7, 2, 1, 9, 5, 3, 4, 8],
    [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3],
    [4, 2, 6, 8, 5, 3, 7, 9, 1],
    [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4],
    [2, 8, 7, 4, 1, 9, 6, 3, 5],
    [3, 4, 5, 2, 8, 6, 1, 7, 9],
]


def test_validate_grid_shape_valid():
    assert validate_grid_shape(VALID_SOLUTION) is None


def test_validate_grid_shape_wrong_outer_length():
    error = validate_grid_shape([[1] * 9] * 8)
    assert error is not None


def test_validate_grid_shape_wrong_row_length():
    grid = [list(row) for row in VALID_SOLUTION]
    grid[3] = grid[3][:8]
    error = validate_grid_shape(grid)
    assert error is not None


def test_validate_grid_shape_zero_not_allowed():
    grid = [list(row) for row in VALID_SOLUTION]
    grid[0][0] = 0
    error = validate_grid_shape(grid)
    assert "1-9" in error or error is not None


def test_validate_grid_shape_value_out_of_range():
    grid = [list(row) for row in VALID_SOLUTION]
    grid[0][0] = 10
    error = validate_grid_shape(grid)
    assert error is not None


def test_validate_grid_shape_non_integer():
    grid = [list(row) for row in VALID_SOLUTION]
    grid[0][0] = "5"
    error = validate_grid_shape(grid)
    assert error is not None


def test_grade_submission_all_correct():
    result = grade_submission(VALID_SOLUTION, VALID_SOLUTION)
    assert result["correct"] is True
    assert all(result["rows_correct"])
    assert all(result["cols_correct"])
    assert all(result["boxes_correct"])


def test_grade_submission_one_wrong_row():
    wrong = [list(row) for row in VALID_SOLUTION]
    wrong[2] = list(reversed(wrong[2]))  # reverse row 2 to make it wrong
    result = grade_submission(wrong, VALID_SOLUTION)
    assert result["correct"] is False
    assert result["rows_correct"][2] is False
    # Other rows unaffected
    assert result["rows_correct"][0] is True


def test_grade_submission_one_wrong_col():
    wrong = [list(row) for row in VALID_SOLUTION]
    # Swap two cells in column 4 to make it wrong
    wrong[0][4], wrong[1][4] = wrong[1][4], wrong[0][4]
    result = grade_submission(wrong, VALID_SOLUTION)
    assert result["correct"] is False
    assert result["cols_correct"][4] is False


def test_grade_submission_returns_9_entries_each():
    result = grade_submission(VALID_SOLUTION, VALID_SOLUTION)
    assert len(result["rows_correct"]) == 9
    assert len(result["cols_correct"]) == 9
    assert len(result["boxes_correct"]) == 9


def test_grade_submission_box_indices():
    # box 0 = rows 0-2, cols 0-2
    wrong = [list(row) for row in VALID_SOLUTION]
    wrong[0][0], wrong[0][1] = wrong[0][1], wrong[0][0]  # swap in box 0
    result = grade_submission(wrong, VALID_SOLUTION)
    assert result["boxes_correct"][0] is False
    # box 8 = rows 6-8, cols 6-8 — untouched
    assert result["boxes_correct"][8] is True


def test_grade_submission_all_cells_wrong():
    all_ones = [[1] * 9 for _ in range(9)]
    result = grade_submission(all_ones, VALID_SOLUTION)
    assert result["correct"] is False
    assert not any(result["rows_correct"])
    assert not any(result["cols_correct"])
    assert not any(result["boxes_correct"])


def test_validate_grid_shape_none_input():
    error = validate_grid_shape(None)
    assert error is not None


def test_validate_grid_shape_empty_list():
    error = validate_grid_shape([])
    assert error is not None


def test_validate_grid_shape_negative_value():
    grid = [list(row) for row in VALID_SOLUTION]
    grid[4][4] = -1
    error = validate_grid_shape(grid)
    assert error is not None
