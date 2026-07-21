from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.auth import router as auth_router
from app.api.router import api_router
from app.core.config import settings
from app.core.database import check_database, close_database
from app.core.redis import check_redis, close_redis
from app.middleware.error_handler import register_exception_handlers
from app.middleware.trace import TraceIdMiddleware
from app.schemas.common import ApiResponse, success


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.check_dependencies_on_startup:
        await check_database()
        await check_redis()
    yield
    await close_redis()
    await close_database()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(auth_router)

    @app.get("/", response_model=ApiResponse[dict[str, str]], include_in_schema=False)
    async def root() -> ApiResponse[dict[str, str]]:
        return success({"service": settings.app_name, "version": __version__})

    return app


app = create_app()
