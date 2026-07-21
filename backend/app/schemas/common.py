from typing import Generic, TypeVar

from pydantic import BaseModel

from app.core.trace import get_trace_id

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "OK"
    message: str = ""
    data: T | None = None
    trace_id: str = ""


def success(data: T | None = None, *, message: str = "") -> ApiResponse[T]:
    return ApiResponse(data=data, message=message, trace_id=get_trace_id())
