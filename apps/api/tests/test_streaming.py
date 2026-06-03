"""Market-hours gating + poll-and-publish (monkeypatched provider)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.redis import get_redis_client
from app.modules.market_data import repository as repo
from app.modules.market_data import streaming
from app.modules.market_data.models import InstrumentSource
from app.modules.market_data.providers.base import CanonicalBar


def test_crypto_is_always_open() -> None:
    # Saturday — crypto still trades.
    assert streaming.is_market_open("24x7", datetime(2024, 1, 6, 3, 0, tzinfo=UTC)) is True


def test_equities_closed_on_weekend() -> None:
    assert streaming.is_market_open("XNYS", datetime(2024, 1, 6, 15, 0, tzinfo=UTC)) is False


def test_equities_open_during_session() -> None:
    assert (
        streaming.is_market_open("XNYS", datetime(2024, 1, 2, 15, 0, tzinfo=UTC)) is True
    )  # 10:00 ET
    assert (
        streaming.is_market_open("XNYS", datetime(2024, 1, 2, 12, 0, tzinfo=UTC)) is False
    )  # pre-open


class _FakeProvider:
    source = "fake"

    def __init__(self, bars: list[CanonicalBar]) -> None:
        self._bars = bars

    async def fetch_bars(self, source_symbol: str, start: datetime, end: datetime):
        return self._bars


async def test_poll_and_publish_upserts_and_publishes(monkeypatch: pytest.MonkeyPatch) -> None:
    async with get_sessionmaker()() as s:
        inst = await repo.get_or_create_instrument(
            s, symbol="BTC/USD", asset_class="crypto", calendar="24x7"
        )
        s.add(
            InstrumentSource(
                instrument_id=inst.id, source="binance", source_symbol="BTC/USDT", is_primary=True
            )
        )
        await s.commit()
        iid = inst.id

    bar_ts = (datetime.now(UTC) - timedelta(minutes=1)).replace(second=0, microsecond=0)
    bars = [
        CanonicalBar(
            ts=bar_ts,
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("1"),
            is_final=True,
            source="binance",
        )
    ]
    monkeypatch.setattr(streaming, "make_provider", lambda source, settings: _FakeProvider(bars))

    async with get_sessionmaker()() as s:
        published = await streaming.poll_and_publish(s, get_redis_client(), get_settings())

    assert published == 1
    assert await get_redis_client().get(f"price:{iid}") == "100"
