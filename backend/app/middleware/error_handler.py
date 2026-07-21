import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException, ErrorCode
from app.core.trace import get_trace_id

logger = logging.getLogger(__name__)


def _payload(code: str, message: str, data: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": get_trace_id(),
    }


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.code, exc.message, exc.data),
    )


async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_payload(
            ErrorCode.INVALID_ARGUMENT,
            "请求参数校验失败",
            {"errors": exc.errors()},
        ),
    )


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = (
        ErrorCode.RESOURCE_NOT_FOUND
        if exc.status_code == 404
        else ErrorCode.INVALID_ARGUMENT
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(code, str(exc.detail)),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_payload(ErrorCode.INTERNAL_ERROR, "系统内部错误，请通过 trace_id 联系管理员"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
