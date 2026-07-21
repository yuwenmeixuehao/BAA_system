import base64
import json
from typing import Any

from app.core.exceptions import AppException, ErrorCode


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if not isinstance(value, dict):
            raise ValueError("cursor must be an object")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppException(
            ErrorCode.INVALID_ARGUMENT,
            "分页游标无效",
            status_code=400,
        ) from exc
