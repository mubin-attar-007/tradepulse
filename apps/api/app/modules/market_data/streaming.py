"""Live quote publishing.

MVP uses a periodic REST poll (reusing the existing adapters) to fetch the
latest closed bars and publish them to Redis for WS fan-out. The provider
interface is the seam to swap in true venue WebSockets (ccxt.pro / Alpaca
stream) later without touching the publish/fan-out path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.modules.market_data import realtime
from app.modules.market_data import repository as repo
from app.modules.market_data.models import Instrument, InstrumentSource
from app.modules.market_data.providers.factory import make_provider

logger = get_logger("streaming")

# XNYS regular session in UTC (ignores holidays/half-days — refined later).
_XNYS_OPEN_MIN = 13 * 60 + 30
_XNYS_CLOSE_MIN = 20 * 60


def is_market_open(calendar: str, now: datetime) -> bool:
    if calendar == "24x7":
        return True
    if now.weekday() >= 5:  # Sat/Sun
        return False
    minutes = now.hour * 60 + now.minute
    return _XNYS_OPEN_MIN <= minutes < _XNYS_CLOSE_MIN


async def poll_and_publish(
    session: AsyncSession, redis: Redis, settings: Settings, *, lookback_minutes: int = 3
) -> int:
    rows = (
        await session.execute(
            select(Instrument, InstrumentSource)
            .join(InstrumentSource, InstrumentSource.instrument_id == Instrument.id)
            .where(Instrument.is_active.is_(True), InstrumentSource.is_primary.is_(True))
        )
    ).all()

    now = datetime.now(UTC)
    published = 0
    for instrument, source in rows:
        if not is_market_open(instrument.calendar, now):
            continue
        provider = make_provider(source.source, settings)
        try:
            bars = await provider.fetch_bars(
                source.source_symbol, now - timedelta(minutes=lookback_minutes), now
            )
        except Exception:
            logger.warning("poll_fetch_failed", symbol=instrument.symbol, source=source.source)
            continue
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                await close()

        closed = repo.normalize_bars([bar for bar in bars if bar.is_final])
        if not closed:
            continue
        await repo.upsert_bars(session, instrument.id, closed)
        latest = repo.BarPoint(
            ts=closed[-1].ts,
            open=closed[-1].open,
            high=closed[-1].high,
            low=closed[-1].low,
            close=closed[-1].close,
            volume=closed[-1].volume,
        )
        await realtime.publish_bar(redis, instrument.id, latest, is_final=True)
        published += 1

    await session.commit()
    logger.info("poll_published", instruments=published)
    return published
