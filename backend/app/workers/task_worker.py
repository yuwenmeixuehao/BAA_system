import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.services.task_service import task_service
from app.workers.cancellation import TaskCancelledError, cancellation_service
from app.workers.task_queue import TaskQueue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerContext:
    task_id: str
    check_cancelled: Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class WorkerOutcome:
    status: Literal["waiting_input", "success"]
    current_step: str | None = None
    clarification_question: str | None = None


class TaskExecutor(Protocol):
    async def execute(self, context: WorkerContext) -> WorkerOutcome: ...


class TaskExecutionError(RuntimeError):
    def __init__(self, error_code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.error_code = error_code
        self.user_message = user_message


class TaskWorker:
    """Consumes queued tasks; the phase-four Agent supplies the executor."""

    def __init__(
        self,
        redis: Redis,
        sessions: async_sessionmaker[AsyncSession],
    ) -> None:
        self.redis = redis
        self.sessions = sessions
        self.queue = TaskQueue(redis)
        self.last_recovery_at = 0.0

    async def process_once(
        self,
        executor: TaskExecutor,
        *,
        block_seconds: int | None = None,
    ) -> bool:
        task_id = await self.queue.reserve(block_seconds)
        if task_id is None:
            return False
        try:
            await self._process(task_id, executor)
        except Exception:
            logger.exception("task worker infrastructure failure", extra={"task_id": task_id})
            await self.queue.release(task_id)
            raise
        else:
            await self.queue.acknowledge(task_id)
        return True

    async def run_forever(self, executor: TaskExecutor) -> None:
        retry_delay_seconds = 1.0
        while True:
            try:
                if (
                    time.monotonic() - self.last_recovery_at
                    >= settings.task_queue_recovery_interval_seconds
                ):
                    await self.recover_queued_tasks()
                await self.process_once(executor)
            except RedisError:
                logger.exception(
                    "worker Redis operation failed; retrying",
                    extra={"retry_delay_seconds": retry_delay_seconds},
                )
                await asyncio.sleep(retry_delay_seconds)
                retry_delay_seconds = min(retry_delay_seconds * 2, 30.0)
            else:
                retry_delay_seconds = 1.0

    async def recover_queued_tasks(self, *, limit: int = 1000) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.clarification_timeout_seconds)
        async with self.sessions() as session:
            expired = await task_service.tasks.list_expired_waiting(
                session,
                updated_before=cutoff,
                limit=limit,
            )
        for task in expired:
            async with self.sessions() as session:
                await task_service.transition(
                    session,
                    self.redis,
                    task.id,
                    "cancelled",
                    error_code="CLARIFICATION_TIMEOUT",
                    error_message="等待补充信息超时，任务已取消",
                )
        async with self.sessions() as session:
            queued = await task_service.tasks.list_queued(session, limit=limit)
        enqueued = 0
        for task in queued:
            enqueued += int(await self.queue.enqueue(task.id))
        self.last_recovery_at = time.monotonic()
        return enqueued

    async def _process(self, task_id: str, executor: TaskExecutor) -> None:
        async with self.sessions() as session:
            task = await task_service.tasks.get_by_id(session, task_id)
            if task is None or task.task_status != "queued":
                return
            if task.cancel_requested:
                await task_service.transition(session, self.redis, task_id, "cancelled")
                return
        async with self.sessions() as session:
            claimed = await task_service.transition(
                session,
                self.redis,
                task_id,
                "running",
                current_step="agent_graph",
            )
        if claimed is None:
            return

        async def check_cancelled() -> None:
            async with self.sessions() as check_session:
                await cancellation_service.raise_if_requested(
                    self.redis,
                    check_session,
                    task_id,
                )

        try:
            await check_cancelled()
            outcome = await executor.execute(
                WorkerContext(task_id=task_id, check_cancelled=check_cancelled)
            )
            await check_cancelled()
            async with self.sessions() as session:
                await task_service.transition(
                    session,
                    self.redis,
                    task_id,
                    outcome.status,
                    current_step=outcome.current_step,
                    clarification_question=outcome.clarification_question,
                )
        except TaskCancelledError:
            async with self.sessions() as session:
                await task_service.transition(session, self.redis, task_id, "cancelled")
        except TaskExecutionError as exc:
            logger.warning(
                "task execution stopped with classified error",
                extra={"task_id": task_id, "error_code": exc.error_code},
            )
            async with self.sessions() as session:
                await task_service.transition(
                    session,
                    self.redis,
                    task_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.user_message,
                )
        except Exception:
            logger.exception("task execution failed", extra={"task_id": task_id})
            async with self.sessions() as session:
                await task_service.transition(
                    session,
                    self.redis,
                    task_id,
                    "failed",
                    error_code="AGENT_EXECUTION_FAILED",
                    error_message="任务执行失败，请稍后重试",
                )


async def run_worker(
    redis: Redis,
    sessions: async_sessionmaker[AsyncSession],
    executor: TaskExecutor,
) -> None:
    await TaskWorker(redis, sessions).run_forever(executor)


def run_worker_sync(
    redis: Redis,
    sessions: async_sessionmaker[AsyncSession],
    executor: TaskExecutor,
) -> None:
    asyncio.run(run_worker(redis, sessions, executor))
