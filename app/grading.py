from typing import Optional

__all__ = ["validate_grid_shape", "grade_submission"]


def validate_grid_shape(grid: list) -> Optional[str]:
    if not isinstance(grid, list) or len(grid) != 9:
        return "Grid must be a 9x9 array with 9 rows"
    for i, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != 9:
            return f"Row {i} must have 9 elements"
        for j, val in enumerate(row):
            if not isinstance(val, int) or val < 1 or val > 9:
                return f"Cell [{i}][{j}] must be an integer 1-9, got {val!r}"
    return None


def grade_submission(
    submitted: list[list[int]], solution: list[list[int]]
) -> dict:
    rows_correct = [submitted[r] == solution[r] for r in range(9)]
    cols_correct = [
        all(submitted[r][c] == solution[r][c] for r in range(9))
        for c in range(9)
    ]
    boxes_correct = [_box_correct(submitted, solution, b) for b in range(9)]
    correct = all(rows_correct) and all(cols_correct) and all(boxes_correct)
    return {
        "correct": correct,
        "rows_correct": rows_correct,
        "cols_correct": cols_correct,
        "boxes_correct": boxes_correct,
    }


def _box_correct(
    submitted: list[list[int]], solution: list[list[int]], box_idx: int
) -> bool:
    # box_idx 0-8, row-major: box 0=top-left, box 2=top-right, box 6=bottom-left
    start_r = (box_idx // 3) * 3
    start_c = (box_idx % 3) * 3
    return all(
        submitted[r][c] == solution[r][c]
        for r in range(start_r, start_r + 3)
        for c in range(start_c, start_c + 3)
    )
