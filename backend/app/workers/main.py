import asyncio

from app.agent.executor import LangGraphTaskExecutor
from app.core.config import settings
from app.core.database import AsyncSessionFactory, close_database
from app.core.redis import close_worker_redis, worker_redis_client
from app.workers.task_worker import run_worker


async def main() -> None:
    executor = LangGraphTaskExecutor(
        worker_redis_client,
        AsyncSessionFactory,
        settings,
    )
    try:
        await run_worker(worker_redis_client, AsyncSessionFactory, executor)
    finally:
        await close_worker_redis()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
