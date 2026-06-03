"""Phase 8 seam: the live gate refuses by default, broker creds encrypt at rest,
and no live-order path executes."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.trading.broker_schemas import BrokerConnectionOut
from app.modules.trading.broker_service import BrokerConnectionService
from app.modules.trading.live_gate import LiveTradingGate


def test_gate_refuses_by_default() -> None:
    status = LiveTradingGate.evaluate(get_settings())
    assert status.allowed is False
    assert "live_feature_disabled" in status.blocked_reasons()
    assert "2fa_not_enabled" in status.blocked_reasons()


def test_connection_out_exposes_no_secret() -> None:
    fields = set(BrokerConnectionOut.model_fields)
    assert "api_key" not in fields and "api_secret" not in fields
    assert "encrypted_credentials" not in fields


async def test_broker_credentials_encrypt_and_roundtrip() -> None:
    async with get_sessionmaker()() as s:
        user = User(email="broker@example.com")
        s.add(user)
        await s.flush()
        conn = await BrokerConnectionService(s, user.id).add(
            broker="alpaca", env="paper", label="my paper", api_key="KEY123", api_secret="SECRET456"
        )
        assert b"KEY123" not in conn.encrypted_credentials  # not stored in plaintext
        key, secret = BrokerConnectionService.decrypt(conn)
        assert key == "KEY123" and secret == "SECRET456"


async def test_tenancy() -> None:
    async with get_sessionmaker()() as s:
        a = User(email="a@example.com")
        b = User(email="b@example.com")
        s.add_all([a, b])
        await s.flush()
        await BrokerConnectionService(s, a.id).add(
            broker="alpaca", env="paper", label=None, api_key="k", api_secret="s"
        )
        await s.commit()
        assert list(await BrokerConnectionService(s, b.id).list()) == []


async def _login(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "l@example.com", "password": "password123"})


async def test_brokers_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/brokers/connections")).status_code == 401


async def test_add_connection_returns_no_secret(client: AsyncClient) -> None:
    await _login(client)
    resp = await client.post(
        "/brokers/connections",
        json={"broker": "alpaca", "env": "paper", "api_key": "KEY", "api_secret": "SECRET"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["broker"] == "alpaca"
    assert "api_key" not in body and "api_secret" not in body


async def test_live_preflight_blocked(client: AsyncClient) -> None:
    await _login(client)
    resp = await client.get("/live/preflight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False and "live_feature_disabled" in body["blocked_reasons"]


async def test_live_order_is_refused(client: AsyncClient) -> None:
    await _login(client)
    import uuid

    resp = await client.post(
        "/live/orders",
        json={"broker_connection_id": str(uuid.uuid4()), "symbol": "AAPL", "side": "buy", "qty": 1},
    )
    assert resp.status_code == 403  # structurally refused by the gate
