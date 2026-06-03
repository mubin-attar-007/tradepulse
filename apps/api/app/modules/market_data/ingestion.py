"""Historical backfill: fetch via a provider, keep only closed bars, upsert.

Idempotent (the upsert dedups), so re-runs are safe. ``resume_start`` uses the
latest stored bar as an implicit watermark. Calendar-aware gap-fill is a
follow-up refinement; correctness here rests on the idempotent upsert.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.market_data import repository as repo
from app.modules.market_data.providers.base import MarketDataProvider

logger = get_logger("ingestion")
_BATCH = 2000


@dataclass(frozen=True, slots=True)
class BackfillResult:
    instrument_id: uuid.UUID
    source: str
    bars_written: int
    first_ts: datetime | None
    last_ts: datetime | None


async def resume_start(
    session: AsyncSession, instrument_id: uuid.UUID, default: datetime
) -> datetime:
    latest = await repo.latest_bar(session, instrument_id)
    return latest.ts + timedelta(minutes=1) if latest is not None else default


async def backfill_instrument(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    source: str,
    provider: MarketDataProvider,
    source_symbol: str,
    start: datetime,
    end: datetime,
) -> BackfillResult:
    logger.info(
        "backfill_start",
        instrument_id=str(instrument_id),
        source=source,
        source_symbol=source_symbol,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    fetched = await provider.fetch_bars(source_symbol, start, end)
    closed = repo.normalize_bars([bar for bar in fetched if bar.is_final])

    written = 0
    for i in range(0, len(closed), _BATCH):
        written += await repo.upsert_bars(session, instrument_id, closed[i : i + _BATCH])
    await session.commit()

    result = BackfillResult(
        instrument_id=instrument_id,
        source=source,
        bars_written=written,
        first_ts=closed[0].ts if closed else None,
        last_ts=closed[-1].ts if closed else None,
    )
    logger.info("backfill_done", instrument_id=str(instrument_id), bars=written)
    return result
