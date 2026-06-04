"""Internal ops endpoints — a worker/shell replacement for free PaaS hosts
(Hugging Face Spaces, Render) that have no always-on background process and no
interactive shell.

- POST /internal/tick      → what the ARQ worker crons do (poll bars + advance
  paper sessions). An external scheduler (cron-job.org) calls it every few minutes.
- POST /internal/backfill  → load historical bars for a symbol (the `just backfill`
  CLI, exposed as an endpoint so it works without a shell).

Both are hidden from the API schema and return 404 unless ``TICK_SECRET`` is set
and the ``key`` matches — so they're never open endpoints.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["ops"])
logger = get_logger("ops")


def _require_secret(key: str) -> None:
    # 404 (not 403) so a disabled/wrong-key request is indistinguishable from
    # "not found". Constant-time compare avoids timing leaks.
    secret = get_settings().tick_secret
    if not secret or not hmac.compare_digest(key, secret):
        raise HTTPException(status_code=404)


@router.post("/internal/tick", include_in_schema=False)
async def tick(key: str = Query(default="")) -> dict[str, Any]:
    _require_secret(key)
    settings = get_settings()

    from app.core.db import get_sessionmaker
    from app.core.redis import get_redis_client
    from app.modules.market_data.streaming import poll_and_publish
    from app.modules.trading.repository import all_running_sessions
    from app.modules.trading.service import PaperService

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        published = await poll_and_publish(session, get_redis_client(), settings)
    async with sessionmaker() as session:
        sessions = await all_running_sessions(session)
        for paper in sessions:
            await PaperService(session, paper.owner_id).run_session(paper)
        await session.commit()
        advanced = len(sessions)

    logger.info("tick", published=published, advanced=advanced)
    return {"published": published, "advanced": advanced}


@router.post("/internal/backfill", include_in_schema=False)
async def backfill(symbol: str, days: int = 2, key: str = Query(default="")) -> dict[str, Any]:
    """Load historical 1m bars for one seeded symbol via its primary provider.
    Lets you seed history on hosts with no shell (HF Spaces). Synchronous; keep
    ``days`` small so it finishes within the host's request timeout."""
    _require_secret(key)
    settings = get_settings()
    days = max(1, min(days, 30))

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.market_data import ingestion
    from app.modules.market_data.models import Instrument, InstrumentSource
    from app.modules.market_data.providers.factory import make_provider

    async with get_sessionmaker()() as session:
        instrument = await session.scalar(select(Instrument).where(Instrument.symbol == symbol))
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"Unknown instrument {symbol!r}")
        source = await session.scalar(
            select(InstrumentSource).where(
                InstrumentSource.instrument_id == instrument.id,
                InstrumentSource.is_primary.is_(True),
            )
        )
        if source is None:
            raise HTTPException(status_code=400, detail=f"No primary source for {symbol!r}")
        provider = make_provider(source.source, settings)
        try:
            end = datetime.now(UTC)
            result = await ingestion.backfill_instrument(
                session,
                instrument_id=instrument.id,
                source=source.source,
                provider=provider,
                source_symbol=source.source_symbol,
                start=end - timedelta(days=days),
                end=end,
            )
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                await close()

    logger.info("backfill", symbol=symbol, bars=result.bars_written, source=result.source)
    return {"symbol": symbol, "bars_written": result.bars_written, "source": result.source}
