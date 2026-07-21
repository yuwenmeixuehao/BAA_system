from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.exceptions import AppException, ErrorCode
from app.core.redis import get_redis
from app.schemas.common import ApiResponse, success
from app.services.auth_service import auth_service
from app.services.oidc_service import oidc_service
from app.services.session_service import session_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _safe_redirect(path: str | None) -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/workbench"
    return path


@router.get("/login", response_class=RedirectResponse)
async def login(
    redis: Annotated[Redis, Depends(get_redis)],
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    authorization_url = await oidc_service.create_authorization_url(
        redis,
        _safe_redirect(next_path),
    )
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/callback", response_class=RedirectResponse)
async def callback(
    redis: Annotated[Redis, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise AppException(ErrorCode.UNAUTHORIZED, f"OIDC 登录失败：{error}", status_code=401)
    if not code or not state:
        raise AppException(ErrorCode.INVALID_ARGUMENT, "OIDC 回调参数不完整", status_code=400)
    claims, redirect_to = await oidc_service.exchange_code(redis, code, state)
    user = await auth_service.map_user(session, claims)
    token = await session_service.create(redis, user.id)
    response = RedirectResponse(
        f"{settings.frontend_base_url.rstrip('/')}{_safe_redirect(redirect_to)}",
        status_code=303,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=settings.session_cookie_http_only,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_same_site,
        path="/",
    )
    return response


@router.post("/logout", response_model=ApiResponse[dict[str, bool]])
async def logout(
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
) -> ApiResponse[dict[str, bool]]:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await session_service.revoke(redis, token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=settings.session_cookie_http_only,
        samesite=settings.session_cookie_same_site,
    )
    return success({"logged_out": True})
