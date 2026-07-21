from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self) -> None:
        self.users = UserRepository()

    async def map_user(self, session: AsyncSession, claims: dict[str, Any]) -> User:
        external_id = str(claims["sub"])[:255]
        user = await self.users.get_by_external_id(session, external_id)
        username = self._optional_text(claims.get("preferred_username"), 100)
        email = self._optional_text(claims.get("email"), 320)
        display_name = (
            self._optional_text(claims.get("name"), 100)
            or username
            or email
            or external_id[:100]
        )
        if user is None:
            user = User(
                external_user_id=external_id,
                username=username,
                email=email,
                display_name=display_name,
                role="user",
                status="active",
            )
            session.add(user)
        else:
            user.username = username
            user.email = email
            user.display_name = display_name
        user.last_login_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    def _optional_text(value: Any, length: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:length] or None


auth_service = AuthService()
