from typing import Any

from pydantic import BaseModel, Field


class QueryLimits(BaseModel):
    max_returned_rows: int = Field(default=10_000, ge=1, le=200_000)
    max_scanned_rows: int = Field(default=5_000_000, ge=1, le=100_000_000)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class QueryRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=4_000)
    user_question: str | None = Field(default=None, min_length=1, max_length=4_000)
    user_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    task_id: str = Field(min_length=1, max_length=100)
    trace_id: str = Field(min_length=1, max_length=128)
    limits: QueryLimits = Field(default_factory=QueryLimits)


class QueryResponse(BaseModel):
    sql: str
    rows: list[dict[str, Any]]
    scanned_rows: int
    columns: list[str]
    truncated: bool = False


class SqlCandidate(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(default="", max_length=1_000)
