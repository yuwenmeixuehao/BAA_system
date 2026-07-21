from redis.asyncio import Redis

from app.core.config import settings


class TaskQueue:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.ready_key = settings.task_queue_name
        self.processing_key = f"{settings.task_queue_name}:processing"

    def marker_key(self, task_id: str) -> str:
        return f"{settings.task_queue_name}:enqueued:{task_id}"

    async def enqueue(self, task_id: str) -> bool:
        marker = self.marker_key(task_id)
        claimed = await self.redis.set(
            marker,
            "1",
            nx=True,
            ex=settings.task_queue_marker_ttl_seconds,
        )
        if not claimed:
            return False
        try:
            await self.redis.lrem(self.processing_key, 0, task_id)
            await self.redis.lpush(self.ready_key, task_id)
        except Exception:
            await self.redis.delete(marker)
            raise
        return True

    async def reserve(self, block_seconds: int | None = None) -> str | None:
        task_id = await self.redis.brpoplpush(
            self.ready_key,
            self.processing_key,
            timeout=block_seconds or settings.task_worker_block_timeout_seconds,
        )
        return str(task_id) if task_id else None

    async def acknowledge(self, task_id: str) -> None:
        await self.redis.lrem(self.processing_key, 1, task_id)
        await self.redis.delete(self.marker_key(task_id))

    async def release(self, task_id: str) -> None:
        removed = await self.redis.lrem(self.processing_key, 1, task_id)
        if removed:
            await self.redis.rpush(self.ready_key, task_id)
