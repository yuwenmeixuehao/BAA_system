import asyncio

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app import __version__
from app.core.config import settings
from app.core.database import check_database
from app.core.redis import check_redis
from app.core.trace import get_trace_id
from app.schemas.common import ApiResponse, success

router = APIRouter(prefix="/health", tags=["health"])


class LiveHealth(BaseModel):
    status: str
    service: str
    version: str


class DependencyComponents(BaseModel):
    mysql: bool
    redis: bool


class ReadyHealth(BaseModel):
    status: str
    components: DependencyComponents


@router.get("/live", response_model=ApiResponse[LiveHealth])
async def live() -> ApiResponse[LiveHealth]:
    return success(
        LiveHealth(status="ok", service=settings.app_name, version=__version__),
    )


@router.get(
    "/ready",
    response_model=ApiResponse[ReadyHealth],
    responses={503: {"model": ApiResponse[ReadyHealth]}},
)
async def ready(response: Response) -> ApiResponse[ReadyHealth]:
    database_ok, redis_ok = await asyncio.gather(check_database(), check_redis())
    ready_status = database_ok and redis_ok
    if not ready_status:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ApiResponse(
        code="OK" if ready_status else "DEPENDENCY_UNAVAILABLE",
        message="" if ready_status else "基础依赖尚未就绪",
        data=ReadyHealth(
            status="ready" if ready_status else "not_ready",
            components=DependencyComponents(mysql=database_ok, redis=redis_ok),
        ),
        trace_id=get_trace_id(),
    )
