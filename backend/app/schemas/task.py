from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

TaskStatus = Literal[
    "queued",
    "running",
    "waiting_input",
    "success",
    "failed",
    "cancelled",
]


class TaskSummary(BaseModel):
    task_id: str
    conversation_id: str
    message_id: str
    client_msg_id: str
    task_status: TaskStatus
    current_step: str | None
    cancel_requested: bool
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class CancelTaskResult(BaseModel):
    task_id: str
    task_status: TaskStatus
    cancel_requested: bool
    accepted: bool


class TaskEventItem(BaseModel):
    type: str
    task_id: str
    conversation_id: str
    event_seq: int
    occurred_at: datetime
    payload: dict[str, Any]


class TaskEventList(BaseModel):
    items: list[TaskEventItem]
    last_event_seq: int
