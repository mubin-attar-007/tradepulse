"""Market-data persistence + the point-in-time read contract.

Closed-bar discipline (invariant #3) is enforced at the source: every read here
returns only ``is_final`` bars, so look-ahead is structurally impossible. The
backtest/paper services read a window via ``get_bars``; ``bars_as_of`` adds an
explicit point-in-time cutoff for replay scenarios that need to reconstruct what
was visible at an instant. Higher timeframes are derived on the fly with portable
SQL (``date_bin`` aggregation — works on plain Postgres or TimescaleDB); we never
duplicate raw 1-minute data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market_data.models import OHLCV, Instrument
from app.modules.market_data.providers.base import CanonicalBar

_BAR = timedelta(minutes=1)  # MVP stores 1-minute bars only

# Map a UI timeframe to a Postgres interval literal for date_bin() aggregation.
_TIMEFRAME_INTERVALS: dict[str, str] = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}


@dataclass(frozen=True, slots=True)
class BarPoint:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


async def get_or_create_instrument(
    session: AsyncSession, *, symbol: str, asset_class: str, **kwargs: object
) -> Instrument:
    existing = await session.scalar(
        select(Instrument).where(Instrument.symbol == symbol, Instrument.asset_class == asset_class)
    )
    if existing is not None:
        return existing
    instrument = Instrument(symbol=symbol, asset_class=asset_class, **kwargs)
    session.add(instrument)
    await session.flush()
    return instrument


async def upsert_bars(
    session: AsyncSession, instrument_id: uuid.UUID, bars: Iterable[CanonicalBar]
) -> int:
    """Idempotent multi-row upsert. Forming bars may be overwritten; once a bar
    is ``is_final`` it is immutable (a re-ingest is a no-op)."""
    rows = [
        {
            "instrument_id": instrument_id,
            "ts": bar.ts,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "is_final": bar.is_final,
            "source": bar.source,
        }
        for bar in bars
    ]
    if not rows:
        return 0
    stmt = pg_insert(OHLCV).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "ts"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "is_final": stmt.excluded.is_final,
            "source": stmt.excluded.source,
        },
        where=OHLCV.is_final.is_(False),  # never mutate an already-final bar
    )
    await session.execute(stmt)
    return len(rows)


async def bars_as_of(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    as_of: datetime,
    *,
    limit: int | None = None,
) -> list[BarPoint]:
    """Point-in-time read: only bars fully closed by ``as_of`` (look-ahead-safe).

    A 1-minute bar opening at ``ts`` closes at ``ts + 1m``; it is knowable at
    ``as_of`` only if ``ts + 1m <= as_of`` (i.e. ``ts <= as_of - 1m``).
    """
    cutoff = as_of - _BAR
    stmt = (
        select(OHLCV)
        .where(
            OHLCV.instrument_id == instrument_id,
            OHLCV.is_final.is_(True),
            OHLCV.ts <= cutoff,
        )
        .order_by(OHLCV.ts)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [BarPoint(r.ts, r.open, r.high, r.low, r.close, r.volume) for r in result.scalars()]


async def get_bars(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    *,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[BarPoint]:
    """History for charts. ``1m`` reads raw; higher timeframes aggregate on the
    fly with portable ``date_bin`` SQL (no duplicated storage)."""
    if timeframe == "1m":
        stmt = (
            select(OHLCV)
            .where(
                OHLCV.instrument_id == instrument_id,
                OHLCV.is_final.is_(True),
                OHLCV.ts >= start,
                OHLCV.ts < end,
            )
            .order_by(OHLCV.ts)
        )
        result = await session.execute(stmt)
        return [BarPoint(r.ts, r.open, r.high, r.low, r.close, r.volume) for r in result.scalars()]

    interval = _TIMEFRAME_INTERVALS.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    # `interval` is from a fixed whitelist above, so inlining it is injection-safe
    # (asyncpg cannot bind a string to an interval-typed parameter). Uses only
    # standard Postgres — date_bin (PG14+) for bucketing and ordered array_agg for
    # first-open / last-close — so it runs identically on plain Postgres and on
    # TimescaleDB (no time_bucket/first/last dependency). The UTC origin keeps
    # hourly/daily buckets aligned regardless of the DB session timezone.
    query = text(
        f"""
        SELECT date_bin(INTERVAL '{interval}', ts, TIMESTAMPTZ '1970-01-01 00:00:00+00') AS bucket,
               (array_agg(open ORDER BY ts ASC))[1]   AS open,
               max(high)                               AS high,
               min(low)                                AS low,
               (array_agg(close ORDER BY ts DESC))[1]  AS close,
               sum(volume)                             AS volume
        FROM ohlcv
        WHERE instrument_id = :iid AND is_final AND ts >= :start AND ts < :end
        GROUP BY bucket
        ORDER BY bucket
        """
    )
    result = await session.execute(query, {"iid": instrument_id, "start": start, "end": end})
    return [
        BarPoint(row.bucket, row.open, row.high, row.low, row.close, row.volume) for row in result
    ]


async def latest_bar(session: AsyncSession, instrument_id: uuid.UUID) -> BarPoint | None:
    row = await session.scalar(
        select(OHLCV)
        .where(OHLCV.instrument_id == instrument_id, OHLCV.is_final.is_(True))
        .order_by(OHLCV.ts.desc())
        .limit(1)
    )
    if row is None:
        return None
    return BarPoint(row.ts, row.open, row.high, row.low, row.close, row.volume)


def normalize_bars(rows: Sequence[CanonicalBar]) -> list[CanonicalBar]:
    """Sort oldest-first and drop duplicate timestamps (keep last seen)."""
    by_ts: dict[datetime, CanonicalBar] = {bar.ts: bar for bar in rows}
    return [by_ts[ts] for ts in sorted(by_ts)]
