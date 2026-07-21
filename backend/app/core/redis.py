from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=settings.redis_socket_timeout_seconds,
    socket_timeout=settings.redis_socket_timeout_seconds,
)

worker_redis_client: Redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=settings.redis_socket_timeout_seconds,
    socket_timeout=settings.effective_worker_redis_socket_timeout_seconds,
    health_check_interval=30,
)


async def get_redis() -> Redis:
    return redis_client


async def check_redis() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    await redis_client.aclose()


async def close_worker_redis() -> None:
    await worker_redis_client.aclose()
