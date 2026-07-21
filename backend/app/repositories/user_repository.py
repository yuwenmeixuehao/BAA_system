from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User


class UserRepository:
    async def get_by_id(self, session: AsyncSession, user_id: str) -> User | None:
        return await session.scalar(select(User).where(User.id == user_id))

    async def get_by_external_id(
        self,
        session: AsyncSession,
        external_user_id: str,
    ) -> User | None:
        return await session.scalar(
            select(User).where(User.external_user_id == external_user_id)
        )
