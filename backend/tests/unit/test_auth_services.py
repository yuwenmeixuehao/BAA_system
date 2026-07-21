import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.core.config import settings
from app.core.exceptions import AppException
from app.services.oidc_service import OidcService
from app.services.session_service import SessionService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def setex(self, key: str, _: int, value: str) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def expire(self, _: str, __: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_oidc_authorization_url_contains_pkce_and_server_state(monkeypatch) -> None:
    service = OidcService()
    redis = FakeRedis()
    monkeypatch.setattr(settings, "oidc_issuer", "https://identity.example.com")
    monkeypatch.setattr(settings, "oidc_client_id", "insight-agent")

    async def metadata() -> dict[str, str]:
        return {"authorization_endpoint": "https://identity.example.com/authorize"}

    monkeypatch.setattr(service, "_get_metadata", metadata)
    url = await service.create_authorization_url(redis, "/workbench/demo")  # type: ignore[arg-type]
    query = parse_qs(urlparse(url).query)

    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query
    state = query["state"][0]
    state_data = json.loads(redis.values[f"oidc:state:{state}"])
    assert state_data["redirect_to"] == "/workbench/demo"
    assert state_data["nonce"] == query["nonce"][0]
    assert "verifier" in state_data


@pytest.mark.asyncio
async def test_id_token_signature_claims_and_nonce_are_verified(monkeypatch) -> None:
    service = OidcService()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-key"
    monkeypatch.setattr(settings, "oidc_issuer", "https://identity.example.com")
    monkeypatch.setattr(settings, "oidc_client_id", "insight-agent")

    async def jwks(_: str) -> dict[str, list[dict[str, str]]]:
        return {"keys": [jwk]}

    monkeypatch.setattr(service, "_get_jwks", jwks)
    token = jwt.encode(
        {
            "sub": "oidc-user-1",
            "iss": "https://identity.example.com",
            "aud": "insight-agent",
            "nonce": "expected-nonce",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    metadata = {
        "issuer": "https://identity.example.com",
        "jwks_uri": "https://identity.example.com/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    claims = await service._validate_id_token(token, "expected-nonce", metadata)
    assert claims["sub"] == "oidc-user-1"
    with pytest.raises(AppException):
        await service._validate_id_token(token, "wrong-nonce", metadata)


@pytest.mark.asyncio
async def test_local_session_is_stored_by_hash(monkeypatch) -> None:
    redis = FakeRedis()
    service = SessionService()
    monkeypatch.setattr(settings, "session_ttl_seconds", 3600)

    token = await service.create(redis, "user-1")  # type: ignore[arg-type]

    assert token not in redis.values
    assert await service.resolve(redis, token) == "user-1"  # type: ignore[arg-type]
    await service.revoke(redis, token)  # type: ignore[arg-type]
    assert await service.resolve(redis, token) is None  # type: ignore[arg-type]
