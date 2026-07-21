from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.redis import get_redis
from app.dependencies.auth import CurrentUserDep
from app.schemas.common import ApiResponse, success
from app.schemas.task import CancelTaskResult, TaskEventList, TaskSummary
from app.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}/events", response_model=ApiResponse[TaskEventList])
async def list_task_events(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    after_seq: Annotated[int, Query(ge=0)] = 0,
) -> ApiResponse[TaskEventList]:
    return success(
        await task_service.list_events_owned(
            session,
            task_id,
            user.id,
            after_seq=after_seq,
        )
    )


@router.get("/{task_id}", response_model=ApiResponse[TaskSummary])
async def get_task(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[TaskSummary]:
    return success(await task_service.get_owned(session, task_id, user.id))


@router.post("/{task_id}/cancel", response_model=ApiResponse[CancelTaskResult])
async def cancel_task(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ApiResponse[CancelTaskResult]:
    return success(await task_service.cancel(session, redis, task_id, user.id))


@router.post("/{task_id}/retry", response_model=ApiResponse[TaskSummary])
async def retry_task(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ApiResponse[TaskSummary]:
    return success(await task_service.retry(session, redis, task_id, user.id))
