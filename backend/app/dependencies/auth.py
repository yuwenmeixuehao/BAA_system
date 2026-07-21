from typing import Annotated

from fastapi import Cookie, Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.exceptions import AppException, ErrorCode
from app.core.redis import get_redis
from app.models.entities import User
from app.repositories.user_repository import UserRepository
from app.services.session_service import session_service


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> User:
    if not session_token:
        raise AppException(ErrorCode.UNAUTHORIZED, "请先登录", status_code=401)
    try:
        user_id = await session_service.resolve(redis, session_token)
    except RedisError as exc:
        raise AppException(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "会话服务暂不可用",
            status_code=503,
        ) from exc
    if not user_id:
        raise AppException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录", status_code=401)
    user = await UserRepository().get_by_id(session, user_id)
    if user is None or user.status != "active":
        raise AppException(ErrorCode.UNAUTHORIZED, "用户不存在或已停用", status_code=401)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> User:
    if user.role != "admin":
        raise AppException(ErrorCode.FORBIDDEN, "需要管理员权限", status_code=403)
    return user


AdminUserDep = Annotated[User, Depends(require_admin)]
