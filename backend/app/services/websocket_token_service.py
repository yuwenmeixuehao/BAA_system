import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.models.entities import WebsocketToken
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.websocket import WebsocketTokenResponse


class WebsocketTokenService:
    key_prefix = "insight:ws_token:"

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def issue(
        self,
        session: AsyncSession,
        redis: Redis,
        user_id: str,
        conversation_id: str,
    ) -> WebsocketTokenResponse:
        conversation = await ConversationRepository().get_owned(
            session,
            conversation_id,
            user_id,
        )
        if conversation is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "会话不存在", status_code=404)
        token = secrets.token_urlsafe(48)
        digest = self._digest(token)
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.websocket_token_ttl_seconds)
        session.add(
            WebsocketToken(
                user_id=user_id,
                conversation_id=conversation_id,
                token_hash=digest,
                expires_at=expires_at,
            )
        )
        await session.commit()
        payload = json.dumps(
            {"user_id": user_id, "conversation_id": conversation_id},
            separators=(",", ":"),
        )
        try:
            await redis.setex(
                f"{self.key_prefix}{digest}",
                settings.websocket_token_ttl_seconds,
                payload,
            )
        except RedisError as exc:
            raise AppException(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "实时通信鉴权服务暂不可用",
                status_code=503,
            ) from exc
        return WebsocketTokenResponse(
            websocket_token=token,
            expires_in=settings.websocket_token_ttl_seconds,
        )

    async def consume(
        self,
        session: AsyncSession,
        redis: Redis,
        token: str,
        conversation_id: str,
    ) -> str:
        digest = self._digest(token)
        try:
            raw = await redis.getdel(f"{self.key_prefix}{digest}")
        except RedisError as exc:
            raise AppException(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "实时通信鉴权服务暂不可用",
                status_code=503,
            ) from exc
        if not raw:
            raise AppException(
                ErrorCode.UNAUTHORIZED,
                "WebSocket Token 无效、已过期或已使用",
                status_code=401,
            )
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AppException(
                ErrorCode.UNAUTHORIZED,
                "WebSocket Token 无效",
                status_code=401,
            ) from exc
        if payload.get("conversation_id") != conversation_id:
            raise AppException(
                ErrorCode.FORBIDDEN,
                "WebSocket Token 与会话不匹配",
                status_code=403,
            )
        now = datetime.now(UTC)
        record = await session.scalar(
            select(WebsocketToken)
            .where(
                WebsocketToken.token_hash == digest,
                WebsocketToken.user_id == payload.get("user_id"),
                WebsocketToken.conversation_id == conversation_id,
                WebsocketToken.consumed_at.is_(None),
                WebsocketToken.expires_at > now,
            )
            .with_for_update()
        )
        if record is None:
            raise AppException(ErrorCode.UNAUTHORIZED, "WebSocket Token 无效", status_code=401)
        record.consumed_at = now
        await session.commit()
        return record.user_id


websocket_token_service = WebsocketTokenService()
