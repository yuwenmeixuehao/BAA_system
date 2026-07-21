import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode

logger = logging.getLogger(__name__)


class OidcService:
    state_key_prefix = "oidc:state:"

    def __init__(self) -> None:
        self._metadata: dict[str, Any] | None = None
        self._metadata_expires_at = 0.0
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    def ensure_configured(self) -> None:
        if not settings.oidc_issuer or not settings.oidc_client_id:
            raise AppException(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "OIDC 尚未配置，请设置 OIDC_ISSUER 和 OIDC_CLIENT_ID",
                status_code=503,
            )

    async def create_authorization_url(self, redis: Redis, redirect_to: str) -> str:
        self.ensure_configured()
        metadata = await self._get_metadata()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        state_payload = json.dumps(
            {"nonce": nonce, "verifier": verifier, "redirect_to": redirect_to}
        )
        await redis.setex(
            f"{self.state_key_prefix}{state}",
            settings.oidc_state_ttl_seconds,
            state_payload,
        )
        params = {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": settings.oidc_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    async def exchange_code(
        self,
        redis: Redis,
        code: str,
        state: str,
    ) -> tuple[dict[str, Any], str]:
        self.ensure_configured()
        raw_state = await redis.getdel(f"{self.state_key_prefix}{state}")
        if not raw_state:
            raise AppException(
                ErrorCode.UNAUTHORIZED,
                "登录状态已失效，请重新登录",
                status_code=401,
            )
        state_data = json.loads(raw_state)
        metadata = await self._get_metadata()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "code_verifier": state_data["verifier"],
        }
        auth: httpx.BasicAuth | None = None
        methods = metadata.get("token_endpoint_auth_methods_supported", [])
        if settings.oidc_client_secret:
            if not methods or "client_secret_basic" in methods:
                auth = httpx.BasicAuth(
                    settings.oidc_client_id,
                    settings.oidc_client_secret,
                )
            else:
                form["client_secret"] = settings.oidc_client_secret

        try:
            async with httpx.AsyncClient(timeout=settings.oidc_http_timeout_seconds) as client:
                response = await client.post(metadata["token_endpoint"], data=form, auth=auth)
                response.raise_for_status()
                tokens = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppException(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "OIDC 令牌交换失败",
                status_code=502,
            ) from exc

        id_token = tokens.get("id_token")
        if not id_token:
            raise AppException(
                ErrorCode.UNAUTHORIZED,
                "OIDC 响应缺少 ID Token",
                status_code=401,
            )
        claims = await self._validate_id_token(id_token, state_data["nonce"], metadata)
        access_token = tokens.get("access_token")
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if access_token and userinfo_endpoint:
            try:
                async with httpx.AsyncClient(timeout=settings.oidc_http_timeout_seconds) as client:
                    response = await client.get(
                        userinfo_endpoint,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    response.raise_for_status()
                    userinfo = response.json()
                if userinfo.get("sub") == claims.get("sub"):
                    claims = {**claims, **userinfo}
            except (httpx.HTTPError, ValueError):
                pass
        return claims, state_data.get("redirect_to", "/workbench")

    async def _validate_id_token(
        self,
        id_token: str,
        expected_nonce: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
            algorithm = header.get("alg")
            allowed = metadata.get("id_token_signing_alg_values_supported", ["RS256"])
            if not algorithm or algorithm == "none" or algorithm not in allowed:
                raise jwt.InvalidAlgorithmError("unsupported signing algorithm")
            jwks = await self._get_jwks(metadata["jwks_uri"])
            key_data = next(
                (item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")),
                None,
            )
            if not key_data:
                self._jwks_expires_at = 0.0
                jwks = await self._get_jwks(metadata["jwks_uri"])
                key_data = next(
                    (
                        item
                        for item in jwks.get("keys", [])
                        if item.get("kid") == header.get("kid")
                    ),
                    None,
                )
            if not key_data:
                raise jwt.InvalidKeyError("signing key not found")
            claims = jwt.decode(
                id_token,
                key=jwt.PyJWK.from_dict(key_data).key,
                algorithms=[algorithm],
                audience=settings.oidc_client_id,
                issuer=metadata.get("issuer", settings.oidc_issuer),
                options={"require": ["exp", "iss", "aud", "sub"]},
                leeway=60,
            )
            nonce = str(claims.get("nonce", ""))
            if not nonce or not secrets.compare_digest(nonce, expected_nonce):
                raise jwt.InvalidTokenError("nonce mismatch")
            if not claims.get("sub"):
                raise jwt.InvalidTokenError("subject missing")
            return claims
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "OIDC ID Token validation failed: type=%s detail=%s",
                type(exc).__name__,
                str(exc),
            )
            raise AppException(
                ErrorCode.UNAUTHORIZED,
                "ID Token 校验失败",
                status_code=401,
            ) from exc

    async def _get_metadata(self) -> dict[str, Any]:
        if self._metadata and self._metadata_expires_at > time.monotonic():
            return self._metadata
        url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        self._metadata = await self._get_json(url, "OIDC 发现文档获取失败")
        self._metadata_expires_at = time.monotonic() + 300
        return self._metadata

    async def _get_jwks(self, url: str) -> dict[str, Any]:
        if self._jwks and self._jwks_expires_at > time.monotonic():
            return self._jwks
        self._jwks = await self._get_json(url, "OIDC 签名密钥获取失败")
        self._jwks_expires_at = time.monotonic() + 300
        return self._jwks

    @staticmethod
    async def _get_json(url: str, error_message: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=settings.oidc_http_timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppException(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                error_message,
                status_code=502,
            ) from exc


oidc_service = OidcService()
