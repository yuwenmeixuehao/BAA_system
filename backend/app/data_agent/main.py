import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import Settings, settings
from app.core.trace import get_trace_id
from app.data_agent.errors import DataAgentError
from app.data_agent.schemas import QueryRequest, QueryResponse
from app.data_agent.service import DataAgentService
from app.middleware.trace import TraceIdMiddleware

logger = logging.getLogger(__name__)


def create_data_agent_app(
    config: Settings = settings,
    *,
    service: DataAgentService | None = None,
) -> FastAPI:
    query_service = service or DataAgentService(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await query_service.close()

    app = FastAPI(
        title="Insight Data Agent",
        version=__version__,
        debug=config.debug,
        lifespan=lifespan,
    )
    app.add_middleware(TraceIdMiddleware)

    @app.exception_handler(DataAgentError)
    async def data_agent_error_handler(_, exc: DataAgentError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "trace_id": get_trace_id(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "DATA_AGENT_INVALID_REQUEST",
                    "message": "Data Agent 请求参数校验失败",
                },
                "trace_id": get_trace_id(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled Data Agent exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "DATA_AGENT_INTERNAL_ERROR",
                    "message": "Data Agent 内部错误",
                },
                "trace_id": get_trace_id(),
            },
        )

    async def authorize(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = config.data_agent_api_key
        if not expected:
            raise DataAgentError(
                "DATA_AGENT_AUTH_NOT_CONFIGURED",
                "Data Agent 服务鉴权密钥未配置",
                status_code=503,
            )
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
            raise DataAgentError(
                "DATA_AGENT_UNAUTHORIZED",
                "Data Agent 鉴权失败",
                status_code=401,
            )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok", "service": "data-agent", "version": __version__}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        is_ready, components = await query_service.ready()
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"status": "ready" if is_ready else "not_ready", "components": components},
        )

    @app.post("/query", response_model=QueryResponse)
    async def query(
        body: QueryRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> QueryResponse:
        return await query_service.query(body)

    return app


app = create_data_agent_app()
