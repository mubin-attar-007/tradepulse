"""The closed-bar contract for derived timeframes (regression for the forming-bucket bug).

Only 1-minute bars are stored; every higher timeframe is aggregated on read. That
aggregation used to return the CURRENT, still-forming bucket as though it were a
finished bar — at 09:18 UTC the "09:00 hourly bar" held 18 of its 60 minutes and was
handed to the engine, the signal card, and the public reference backtest alike.
Every one of those surfaces then made a decision on an unfinished bar, which is
precisely what invariant #3 exists to prevent, and it affected ALL the timeframes
the product actually defaults to (the public pages and the reference run are 1h).

A second, quieter bug lived in the same query: a window starting mid-bucket built
that bucket out of only its tail, so the reported open/high/low were wrong for the
first bar of every chart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.db import get_sessionmaker
from app.modules.market_data import repository as repo
from app.modules.market_data.providers.base import CanonicalBar

ANCHOR = datetime(2024, 3, 5, 0, 0, tzinfo=UTC)


async def _seed_minutes(session, minutes: int, *, start: datetime = ANCHOR):  # type: ignore[no-untyped-def]
    """`minutes` consecutive 1-minute bars with a strictly rising close."""
    instrument = await repo.get_or_create_instrument(
        session, symbol="LIFECYCLE/USD", asset_class="crypto", calendar="24x7"
    )
    bars = [
        CanonicalBar(
            ts=start + timedelta(minutes=i),
            open=Decimal(100 + i),
            high=Decimal(100 + i) + Decimal("2"),
            low=Decimal(100 + i) - Decimal("1"),
            close=Decimal(101 + i),
            volume=Decimal("10"),
            is_final=True,
            source="test",
        )
        for i in range(minutes)
    ]
    await repo.upsert_bars(session, instrument.id, bars)
    await session.commit()
    return instrument


async def test_forming_bucket_is_never_returned() -> None:
    """With 90 minutes of history, only the ONE completed hour may be returned."""
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, 90)
        now = ANCHOR + timedelta(minutes=90)  # 01:30 — the 01:00 hour is half-formed

        hourly = await repo.get_bars(
            session,
            instrument.id,
            timeframe="1h",
            start=ANCHOR,
            end=now,
            now=now,
        )

        assert [b.ts for b in hourly] == [ANCHOR]
        assert hourly[0].bar_count == 60
        # And it is a real, complete hour: open of minute 0, close of minute 59.
        assert hourly[0].open == Decimal("100")
        assert hourly[0].close == Decimal("160")


async def test_bucket_appears_only_once_it_has_fully_elapsed() -> None:
    """The 01:00 bucket must appear at 02:00 and not a minute earlier."""
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, 120)

        just_before = ANCHOR + timedelta(minutes=119)
        at_close = ANCHOR + timedelta(minutes=120)

        early = await repo.get_bars(
            session, instrument.id, timeframe="1h", start=ANCHOR, end=at_close, now=just_before
        )
        on_time = await repo.get_bars(
            session, instrument.id, timeframe="1h", start=ANCHOR, end=at_close, now=at_close
        )

        assert [b.ts for b in early] == [ANCHOR]
        assert [b.ts for b in on_time] == [ANCHOR, ANCHOR + timedelta(hours=1)]


async def test_a_window_starting_mid_bucket_is_not_clipped() -> None:
    """A bucket is built from ALL its bars or not returned at all.

    Requesting from 00:47 must not yield an "hourly bar" assembled from 13 minutes
    with the wrong open, high and low.
    """
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, 120)
        now = ANCHOR + timedelta(minutes=120)

        clipped = await repo.get_bars(
            session,
            instrument.id,
            timeframe="1h",
            start=ANCHOR + timedelta(minutes=47),
            end=now,
            now=now,
        )
        for candle in clipped:
            assert candle.bar_count == 60, "a partially-covered bucket was returned"
        assert clipped[0].open == Decimal("100"), "bucket open came from the middle of the hour"


@pytest.mark.parametrize(("timeframe", "minutes"), [("5m", 5), ("15m", 15), ("4h", 240)])
async def test_completeness_holds_for_every_derived_timeframe(timeframe: str, minutes: int) -> None:
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, minutes * 2 + 3)
        now = ANCHOR + timedelta(minutes=minutes * 2 + 3)
        bars = await repo.get_bars(
            session, instrument.id, timeframe=timeframe, start=ANCHOR, end=now, now=now
        )
        assert len(bars) == 2, f"{timeframe}: expected exactly the 2 completed buckets"
        for candle in bars:
            assert candle.bar_count == minutes
            assert candle.ts + timedelta(minutes=minutes) <= now


async def test_one_minute_reads_are_unaffected() -> None:
    """1m bars are stored, not derived: their lifecycle is already `is_final`."""
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, 10)
        now = ANCHOR + timedelta(minutes=10)
        bars = await repo.get_bars(
            session, instrument.id, timeframe="1m", start=ANCHOR, end=now, now=now
        )
        assert len(bars) == 10
        assert all(b.bar_count == 1 for b in bars)


async def test_a_historical_window_ends_at_its_own_boundary() -> None:
    """When `end` is in the past, completeness is judged against `end`, not `now`.

    Otherwise a backtest over a closed historical window would silently gain a
    bucket that extends past the window it claims to cover.
    """
    async with get_sessionmaker()() as session:
        instrument = await _seed_minutes(session, 200)
        end = ANCHOR + timedelta(minutes=150)  # 02:30
        much_later = ANCHOR + timedelta(days=5)

        bars = await repo.get_bars(
            session, instrument.id, timeframe="1h", start=ANCHOR, end=end, now=much_later
        )
        assert [b.ts for b in bars] == [ANCHOR, ANCHOR + timedelta(hours=1)]
