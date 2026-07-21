import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """Raised at a cooperative cancellation boundary."""


class CancellationService:
    key_prefix = "insight:task_cancel:"

    def __init__(self) -> None:
        self.tasks = TaskRepository()

    async def request(self, redis: Redis, task_id: str) -> None:
        await redis.setex(
            f"{self.key_prefix}{task_id}",
            settings.task_cancel_ttl_seconds,
            "1",
        )

    async def clear(self, redis: Redis, task_id: str) -> None:
        await redis.delete(f"{self.key_prefix}{task_id}")

    async def is_requested(
        self,
        redis: Redis,
        session: AsyncSession,
        task_id: str,
    ) -> bool:
        try:
            if await redis.exists(f"{self.key_prefix}{task_id}"):
                return True
        except RedisError:
            logger.warning(
                "cancellation marker check degraded to database",
                extra={"task_id": task_id},
            )
        task = await self.tasks.get_by_id(session, task_id)
        return bool(task and task.cancel_requested)

    async def raise_if_requested(
        self,
        redis: Redis,
        session: AsyncSession,
        task_id: str,
    ) -> None:
        if await self.is_requested(redis, session, task_id):
            raise TaskCancelledError(task_id)


cancellation_service = CancellationService()
