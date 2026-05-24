from pydantic import BaseModel, Field, field_validator
from typing import Optional


class SubmitAnswerRequest(BaseModel):
    puzzle_token: str
    grid: list[list[int]]
    name: str = Field(max_length=8)

    @field_validator("name", mode="before")
    @classmethod
    def truncate_name(cls, v: str) -> str:
        return v[:8].strip()


class PuzzleResponse(BaseModel):
    puzzle_token: str
    difficulty: str
    date: str
    grid: list[list[int]]
    start_time_utc: str
    notes: str


class SubmitResponseIncorrect(BaseModel):
    correct: bool = False
    rows_correct: list[bool]
    cols_correct: list[bool]
    boxes_correct: list[bool]
    attempts: int
    elapsed_seconds: float
    rank: None = None
    note: str


class SubmitResponseCorrect(BaseModel):
    correct: bool = True
    solve_time_seconds: float
    attempts: int
    rank: int
    first_solver_today: Optional[str] = None
    note: str


class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    solve_time_seconds: float


class FirstSolverInfo(BaseModel):
    name: str
    solved_at_utc: str


class YouInfo(BaseModel):
    name: str
    rank: int
    solve_time_seconds: float


class LeaderboardResponse(BaseModel):
    date: str
    difficulty: str
    first_solver_today: Optional[FirstSolverInfo] = None
    top10: list[LeaderboardEntry]
    you: Optional[YouInfo] = None
