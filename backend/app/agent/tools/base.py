from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ToolContext:
    user_id: str
    conversation_id: str
    task_id: str
    workspace_root: Path
    trace_id: str


class ToolResult(BaseModel):
    ok: bool
    summary: str
    files: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
