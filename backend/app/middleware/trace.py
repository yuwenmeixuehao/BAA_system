from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.trace import reset_trace_id, set_trace_id


def _valid_trace_id(value: str | None) -> bool:
    if value is None or not 8 <= len(value) <= 128:
        return False
    return all(char.isalnum() or char in "-_." for char in value)


class TraceIdMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.header_name = settings.trace_id_header.encode("latin-1")
        self.header_name_lower = self.header_name.lower()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        raw_trace_id: str | None = None
        for key, value in scope.get("headers", []):
            if key.lower() == self.header_name_lower:
                raw_trace_id = value.decode("latin-1")
                break

        trace_id = raw_trace_id if _valid_trace_id(raw_trace_id) else uuid4().hex
        scope.setdefault("state", {})["trace_id"] = trace_id
        context_token = set_trace_id(trace_id)

        async def send_with_trace(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.header_name, trace_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            reset_trace_id(context_token)
