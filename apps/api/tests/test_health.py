"""Smoke tests: liveness and readiness (DB + Redis reachable)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ready(client: AsyncClient) -> None:
    resp = await client.get("/ready")
    assert resp.status_code == 200
    checks = resp.json()["checks"]
    assert checks["db"] is True
    assert checks["redis"] is True


async def test_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
