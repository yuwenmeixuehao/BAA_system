import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_live_health_uses_unified_response_and_trace_id() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/health/live",
            headers={"X-Trace-ID": "test-trace-001"},
        )

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == "test-trace-001"
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["status"] == "ok"
    assert payload["trace_id"] == "test-trace-001"


@pytest.mark.asyncio
async def test_not_found_uses_unified_error_response() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing-path")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "RESOURCE_NOT_FOUND"
    assert payload["trace_id"]


@pytest.mark.asyncio
async def test_ready_health_uses_typed_unified_response(monkeypatch) -> None:
    async def available() -> bool:
        return True

    monkeypatch.setattr("app.api.health.check_database", available)
    monkeypatch.setattr("app.api.health.check_redis", available)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/health/ready",
            headers={"X-Trace-ID": "ready-trace-001"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "OK",
        "message": "",
        "data": {
            "status": "ready",
            "components": {"mysql": True, "redis": True},
        },
        "trace_id": "ready-trace-001",
    }
