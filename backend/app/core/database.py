from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _create_engine() -> AsyncEngine:
    options: dict[str, object] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }
    if not settings.database_url.startswith("sqlite"):
        options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
    return create_async_engine(settings.database_url, **options)


engine = _create_engine()
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_database() -> None:
    await engine.dispose()
