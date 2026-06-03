"""Charting HTTP endpoints (auth-gated) + Money-as-string serialization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient

from app.core.db import get_sessionmaker
from app.modules.market_data import repository as repo
from app.modules.market_data.providers.base import CanonicalBar

BASE = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


async def _seed() -> uuid.UUID:
    async with get_sessionmaker()() as s:
        inst = await repo.get_or_create_instrument(
            s, symbol="BTC/USD", asset_class="crypto", name="Bitcoin", calendar="24x7"
        )
        bars = [
            CanonicalBar(
                ts=BASE + timedelta(minutes=i),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100.5"),
                volume=Decimal("3"),
                is_final=True,
                source="test",
            )
            for i in range(5)
        ]
        await repo.upsert_bars(s, inst.id, bars)
        await s.commit()
        return inst.id


async def _login(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "trader@example.com", "password": "password123"}
    )


async def test_instruments_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/market/instruments")).status_code == 401


async def test_list_instruments(client: AsyncClient) -> None:
    await _seed()
    await _login(client)
    resp = await client.get("/market/instruments")
    assert resp.status_code == 200
    assert "BTC/USD" in [i["symbol"] for i in resp.json()]


async def test_get_bars_serializes_money_as_string(client: AsyncClient) -> None:
    iid = await _seed()
    await _login(client)
    resp = await client.get(
        f"/market/instruments/{iid}/bars",
        params={
            "timeframe": "1m",
            "start": BASE.isoformat(),
            "end": (BASE + timedelta(minutes=10)).isoformat(),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert data[0]["close"] == "100.50000000"
    assert isinstance(data[0]["close"], str)


async def test_get_bars_unknown_instrument_404(client: AsyncClient) -> None:
    await _login(client)
    resp = await client.get(f"/market/instruments/{uuid.uuid4()}/bars")
    assert resp.status_code == 404


async def test_latest_quote(client: AsyncClient) -> None:
    iid = await _seed()
    await _login(client)
    resp = await client.get(f"/market/instruments/{iid}/latest")
    assert resp.status_code == 200
    assert resp.json()["price"] == "100.50000000"


async def test_ws_ticket_issued(client: AsyncClient) -> None:
    await _login(client)
    resp = await client.post("/market/ws-ticket")
    assert resp.status_code == 200
    assert resp.json()["ticket"]
