"""Market-data spine: idempotent upsert, the look-ahead-safe read contract
(invariant #3), and on-the-fly timeframe aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.modules.market_data import repository as repo
from app.modules.market_data.models import Instrument
from app.modules.market_data.providers.base import CanonicalBar

BASE = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def _bar(
    ts: datetime,
    o: float,
    h: float,
    low: float,
    c: float,
    v: float,
    *,
    final: bool = True,
) -> CanonicalBar:
    return CanonicalBar(
        ts=ts,
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(low)),
        close=Decimal(str(c)),
        volume=Decimal(str(v)),
        is_final=final,
        source="test",
    )


async def _instrument(session: AsyncSession) -> Instrument:
    return await repo.get_or_create_instrument(
        session, symbol="AAPL", asset_class="equity", exchange="XNAS"
    )


async def test_idempotent_upsert() -> None:
    async with get_sessionmaker()() as s:
        inst = await _instrument(s)
        bars = [_bar(BASE + timedelta(minutes=i), 100, 101, 99, 100, 10) for i in range(3)]
        await repo.upsert_bars(s, inst.id, bars)
        await repo.upsert_bars(s, inst.id, bars)  # re-ingest is a no-op
        await s.commit()
        rows = await repo.get_bars(
            s, inst.id, timeframe="1m", start=BASE, end=BASE + timedelta(minutes=10)
        )
        assert len(rows) == 3


async def test_forming_bar_updates_then_final_is_immutable() -> None:
    async with get_sessionmaker()() as s:
        inst = await _instrument(s)
        await repo.upsert_bars(s, inst.id, [_bar(BASE, 100, 100, 100, 100, 1, final=False)])
        await repo.upsert_bars(s, inst.id, [_bar(BASE, 100, 105, 99, 104, 50, final=True)])
        await s.commit()
        rows = await repo.get_bars(
            s, inst.id, timeframe="1m", start=BASE, end=BASE + timedelta(minutes=1)
        )
        assert len(rows) == 1 and rows[0].close == Decimal("104")

        # A final bar is immutable: re-ingest must not change it.
        await repo.upsert_bars(s, inst.id, [_bar(BASE, 1, 1, 1, 1, 999, final=True)])
        await s.commit()
        rows = await repo.get_bars(
            s, inst.id, timeframe="1m", start=BASE, end=BASE + timedelta(minutes=1)
        )
        assert rows[0].close == Decimal("104")


async def test_bars_as_of_is_lookahead_safe() -> None:
    async with get_sessionmaker()() as s:
        inst = await _instrument(s)
        bars = [_bar(BASE + timedelta(minutes=i), 100, 100, 100, 100, 1) for i in range(5)]
        await repo.upsert_bars(s, inst.id, bars)
        await s.commit()

        # At 15:03, only bars closing at/before 15:03 are knowable: 15:00, 15:01, 15:02.
        got = await repo.bars_as_of(s, inst.id, BASE + timedelta(minutes=3))
        assert [b.ts for b in got] == [
            BASE,
            BASE + timedelta(minutes=1),
            BASE + timedelta(minutes=2),
        ]

        # One minute later the 15:03 bar (closing 15:04) becomes available.
        later = await repo.bars_as_of(s, inst.id, BASE + timedelta(minutes=4))
        assert (BASE + timedelta(minutes=3)) in [b.ts for b in later]


async def test_bars_as_of_excludes_forming_bars() -> None:
    async with get_sessionmaker()() as s:
        inst = await _instrument(s)
        await repo.upsert_bars(s, inst.id, [_bar(BASE, 100, 100, 100, 100, 1, final=False)])
        await s.commit()
        # Even an hour later, a never-finalized bar must never drive a decision.
        got = await repo.bars_as_of(s, inst.id, BASE + timedelta(hours=1))
        assert got == []


async def test_time_bucket_aggregation() -> None:
    async with get_sessionmaker()() as s:
        inst = await _instrument(s)
        bars = []
        for i in range(10):
            price = 100 + i
            bars.append(
                _bar(BASE + timedelta(minutes=i), price, price + 2, price - 1, price + 0.5, 10)
            )
        await repo.upsert_bars(s, inst.id, bars)
        await s.commit()

        out = await repo.get_bars(
            s, inst.id, timeframe="5m", start=BASE, end=BASE + timedelta(minutes=10)
        )
        assert len(out) == 2
        first = out[0]
        assert first.ts == BASE
        assert first.open == Decimal("100")  # first open in the bucket
        assert first.close == Decimal("104.5")  # last close (minute 4)
        assert first.high == Decimal("106")  # max high
        assert first.low == Decimal("99")  # min low
        assert first.volume == Decimal("50")  # sum of 5 bars
