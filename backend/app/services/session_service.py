import hashlib
import secrets

from redis.asyncio import Redis

from app.core.config import settings


class SessionService:
    key_prefix = "auth:session:"

    @staticmethod
    def _key(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{SessionService.key_prefix}{digest}"

    async def create(self, redis: Redis, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        await redis.setex(self._key(token), settings.session_ttl_seconds, user_id)
        return token

    async def resolve(self, redis: Redis, token: str) -> str | None:
        user_id = await redis.get(self._key(token))
        if user_id:
            await redis.expire(self._key(token), settings.session_ttl_seconds)
        return user_id

    async def revoke(self, redis: Redis, token: str) -> None:
        await redis.delete(self._key(token))


session_service = SessionService()
