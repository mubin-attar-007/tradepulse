"""Historical backfill: persistence, idempotency, forming-bar skip, resume."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.db import get_sessionmaker
from app.modules.market_data import ingestion
from app.modules.market_data import repository as repo
from app.modules.market_data.providers.base import CanonicalBar

BASE = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def _bars(n: int, *, final: bool = True) -> list[CanonicalBar]:
    return [
        CanonicalBar(
            ts=BASE + timedelta(minutes=i),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("1"),
            is_final=final,
            source="fake",
        )
        for i in range(n)
    ]


class FakeProvider:
    source = "fake"

    def __init__(self, bars: list[CanonicalBar]) -> None:
        self._bars = bars

    async def fetch_bars(
        self, source_symbol: str, start: datetime, end: datetime
    ) -> list[CanonicalBar]:
        return [b for b in self._bars if start <= b.ts < end]


async def test_backfill_persists_and_is_idempotent() -> None:
    async with get_sessionmaker()() as s:
        inst = await repo.get_or_create_instrument(s, symbol="BTC/USD", asset_class="crypto")
        provider = FakeProvider(_bars(5))
        end = BASE + timedelta(minutes=10)
        result = await ingestion.backfill_instrument(
            s,
            instrument_id=inst.id,
            source="fake",
            provider=provider,
            source_symbol="BTC/USDT",
            start=BASE,
            end=end,
        )
        assert result.bars_written == 5
        # Re-run is a no-op; row count stays at 5.
        await ingestion.backfill_instrument(
            s,
            instrument_id=inst.id,
            source="fake",
            provider=provider,
            source_symbol="BTC/USDT",
            start=BASE,
            end=end,
        )
        rows = await repo.get_bars(s, inst.id, timeframe="1m", start=BASE, end=end)
        assert len(rows) == 5


async def test_backfill_skips_forming_bars() -> None:
    async with get_sessionmaker()() as s:
        inst = await repo.get_or_create_instrument(s, symbol="ETH/USD", asset_class="crypto")
        provider = FakeProvider(_bars(3, final=False))
        result = await ingestion.backfill_instrument(
            s,
            instrument_id=inst.id,
            source="fake",
            provider=provider,
            source_symbol="ETH/USDT",
            start=BASE,
            end=BASE + timedelta(minutes=10),
        )
        assert result.bars_written == 0


async def test_resume_start_uses_latest_bar() -> None:
    async with get_sessionmaker()() as s:
        inst = await repo.get_or_create_instrument(s, symbol="BTC/USD", asset_class="crypto")
        await repo.upsert_bars(s, inst.id, _bars(3))
        await s.commit()
        default = BASE - timedelta(days=1)
        resumed = await ingestion.resume_start(s, inst.id, default)
        assert resumed == BASE + timedelta(minutes=3)  # latest (15:02) + 1 minute
