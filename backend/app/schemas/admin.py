from datetime import datetime

from pydantic import BaseModel


class AdminTaskLogItem(BaseModel):
    log_id: str
    task_id: str
    log_level: str
    log_type: str
    log_content: str
    trace_id: str | None
    duration_ms: int | None
    created_at: datetime


class AdminTaskLogList(BaseModel):
    items: list[AdminTaskLogItem]
