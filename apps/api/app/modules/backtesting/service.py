"""Run a backtest for a StrategySpec over stored history (single-instrument MVP)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.modules.backtesting import engine
from app.modules.backtesting.types import BacktestResult, ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import StrategySpec


def data_fingerprint(instrument_id: object, timeframe: str, bars: Sequence[BarPoint]) -> str:
    """Content fingerprint of the exact bar window a run consumed.

    Hashes EVERY bar's timestamp and OHLCV, not just the endpoints. That matters
    because a corrected or re-backfilled interior bar — including a changed high or
    low, which drives every stop, target and ATR result — must change the
    fingerprint, or a stale cached result would be served as if the data were
    unchanged and a "reproducible" experiment would silently refer to different data.

    O(n) over rows already in memory, so the precision costs nothing worth saving.
    """
    digest = hashlib.sha256()
    digest.update(f"{instrument_id}|{timeframe}|{len(bars)}".encode())
    for bar in bars:
        digest.update(
            f"|{bar.ts.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}".encode()
        )
    return digest.hexdigest()


async def run_backtest(
    session: AsyncSession,
    spec: StrategySpec,
    *,
    start: datetime,
    end: datetime,
    config: ExecutionConfig | None = None,
) -> BacktestResult:
    config = config or ExecutionConfig()
    symbol = spec.universe[0]
    instrument = await session.scalar(select(Instrument).where(Instrument.symbol == symbol))
    if instrument is None:
        raise NotFoundError(f"Unknown instrument {symbol!r}; seed it and backfill first.")

    bars = await md_repo.get_bars(
        session, instrument.id, timeframe=spec.timeframe, start=start, end=end
    )
    if len(bars) < 2:
        raise BadRequestError("Not enough bars in range to backtest; backfill more history.")

    result = engine.run(spec, bars, config, calendar=instrument.calendar)
    result.spec_hash = spec.spec_hash()
    result.data_fingerprint = data_fingerprint(instrument.id, spec.timeframe, bars)
    return result
