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
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market_data.models import OHLCV, Instrument
from app.modules.market_data.providers.base import CanonicalBar

_BAR = timedelta(minutes=1)  # MVP stores 1-minute bars only

# Rows per INSERT statement. 9 bound parameters per row against asyncpg's 32,767
# parameter ceiling allows ~3,640; 2,000 leaves headroom if a column is added.
_UPSERT_CHUNK = 2000

# Map a UI timeframe to (Postgres interval literal for date_bin, duration).
_TIMEFRAME_INTERVALS: dict[str, str] = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}
_TIMEFRAME_DURATIONS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}
# date_bin's origin. Buckets are aligned to the Unix epoch in UTC so a bucket's
# identity never depends on the DB session timezone or the query window.
_BUCKET_ORIGIN = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class BarPoint:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    # Number of 1-minute bars aggregated into this bar. 1 for raw 1m reads; for a
    # derived timeframe it exposes gaps (a 1h crypto bucket should hold 60) without
    # the caller having to re-query. ``None`` when not computed.
    bar_count: int | None = None


def floor_to_bucket(ts: datetime, timeframe: str) -> datetime:
    """Snap ``ts`` down to its bucket start, matching Postgres ``date_bin``.

    Kept in Python so the query can widen its scan to the containing bucket: a
    window that starts mid-bucket must not produce a bar built from only the tail
    of that bucket (which would report a wrong open/high/low).
    """
    duration = _TIMEFRAME_DURATIONS[timeframe]
    elapsed = (ts - _BUCKET_ORIGIN) // duration
    return _BUCKET_ORIGIN + elapsed * duration


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
    # Chunk HERE rather than trusting callers. A multi-row INSERT binds one parameter
    # per column per row, and asyncpg caps a statement at 32,767 parameters — nine
    # columns means ~3,640 rows. Leaving the limit to the caller meant any new call
    # site (a wider poll window, a bulk import, a test seeding a few days of minutes)
    # would fail with an opaque driver-level InterfaceError far from its cause.
    for start in range(0, len(rows), _UPSERT_CHUNK):
        chunk = rows[start : start + _UPSERT_CHUNK]
        stmt = pg_insert(OHLCV).values(chunk)
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
    return [BarPoint(r.ts, r.open, r.high, r.low, r.close, r.volume, 1) for r in result.scalars()]


async def get_bars(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    *,
    timeframe: str,
    start: datetime,
    end: datetime,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[BarPoint]:
    """Closed bars for a window. ``1m`` reads raw; higher timeframes aggregate on
    the fly with portable ``date_bin`` SQL (no duplicated storage).

    CLOSED-BAR CONTRACT (invariant #3). A derived bar is returned only once its
    whole interval has elapsed. Two ways a bucket could otherwise be incomplete —
    both are excluded here:

    * **Still forming.** At 09:18 UTC the 09:00 hourly bucket holds 18 of its 60
      minutes. Returning it as a bar would let the engine, the signal card, and the
      public reference backtest all act on an unfinished bar. The ``HAVING`` clause
      drops any bucket whose end is after ``min(end, now)``.
    * **Clipped by the window.** A window starting at 03:47 would build the 03:00
      bucket from only its last 13 minutes, reporting a wrong open/high/low. The
      scan is therefore widened to ``floor_to_bucket(start)`` so a bucket is either
      built from all the bars it has, or not returned at all.

    ``bar_count`` on each returned bar exposes how many 1-minute bars actually
    backed it, so a caller can see venue gaps rather than silently averaging over
    them. ``limit`` caps the payload to the MOST RECENT ``limit`` bars.
    """
    if timeframe == "1m":
        stmt = (
            select(OHLCV)
            .where(
                OHLCV.instrument_id == instrument_id,
                OHLCV.is_final.is_(True),
                OHLCV.ts >= start,
                OHLCV.ts < end,
            )
            .order_by(OHLCV.ts if limit is None else OHLCV.ts.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = [
            BarPoint(r.ts, r.open, r.high, r.low, r.close, r.volume, 1) for r in result.scalars()
        ]
        return rows if limit is None else rows[::-1]

    interval = _TIMEFRAME_INTERVALS.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    # `interval` is from a fixed whitelist above, so inlining it is injection-safe
    # (asyncpg cannot bind a string to an interval-typed parameter). Uses only
    # standard Postgres — date_bin (PG14+) for bucketing and ordered array_agg for
    # first-open / last-close — so it runs identically on plain Postgres and on
    # TimescaleDB (no time_bucket/first/last dependency). The UTC origin keeps
    # hourly/daily buckets aligned regardless of the DB session timezone.
    # When limited, take the most-recent buckets (ORDER BY bucket DESC LIMIT) and
    # re-sort oldest-first in Python to keep the ascending contract.
    order = "ASC" if limit is None else "DESC"
    limit_clause = "" if limit is None else "LIMIT :limit"
    # A bucket is knowable only once it has fully elapsed in wall-clock terms AND
    # lies inside the requested window.
    cutoff = min(end, now or datetime.now(UTC))
    query = text(
        f"""
        SELECT date_bin(INTERVAL '{interval}', ts, TIMESTAMPTZ '1970-01-01 00:00:00+00') AS bucket,
               (array_agg(open ORDER BY ts ASC))[1]   AS open,
               max(high)                               AS high,
               min(low)                                AS low,
               (array_agg(close ORDER BY ts DESC))[1]  AS close,
               sum(volume)                             AS volume,
               count(*)                                AS bar_count
        FROM ohlcv
        WHERE instrument_id = :iid AND is_final AND ts >= :scan_from AND ts < :end
        GROUP BY bucket
        HAVING date_bin(INTERVAL '{interval}', min(ts), TIMESTAMPTZ '1970-01-01 00:00:00+00')
               + INTERVAL '{interval}' <= :cutoff
        ORDER BY bucket {order}
        {limit_clause}
        """
    )
    params: dict[str, object] = {
        "iid": instrument_id,
        # Widen the scan to the bucket containing `start` so the first bucket is
        # never built from a partial slice of itself.
        "scan_from": floor_to_bucket(start, timeframe),
        "end": end,
        "cutoff": cutoff,
    }
    if limit is not None:
        params["limit"] = limit
    result = await session.execute(query, params)
    rows = [
        BarPoint(row.bucket, row.open, row.high, row.low, row.close, row.volume, int(row.bar_count))
        for row in result
    ]
    return rows if limit is None else rows[::-1]


async def resolve_symbol(session: AsyncSession, symbol: str) -> Instrument | None:
    """Case-insensitive symbol lookup for the public API (URL slugs vary in case).

    Only active instruments are resolvable; ``BTC/USD`` and ``btc-usd``-style
    slugs are normalized by the caller before reaching here. Returns ``None`` when
    no active instrument matches (the router turns that into a 404)."""
    return await session.scalar(
        select(Instrument)
        .where(
            func.lower(Instrument.symbol) == symbol.lower(),
            Instrument.is_active.is_(True),
        )
        .order_by(Instrument.symbol)
        .limit(1)
    )


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
