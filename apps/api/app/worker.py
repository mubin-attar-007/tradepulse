"""ARQ worker entrypoint (``arq app.worker.WorkerSettings``).

Shares the app package with the API process. The market-data ingestion
supervisor (Phase 2) and scheduled jobs will live HERE — never in the API
lifespan — so web deploys never interrupt the live feed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("worker")


async def heartbeat(_ctx: dict[str, Any]) -> str:
    """Trivial job proving the worker path end-to-end."""
    logger.info("worker_heartbeat")
    return "ok"


async def ingest_backfill(
    _ctx: dict[str, Any],
    instrument_id: str,
    source: str,
    source_symbol: str,
    start_iso: str,
    end_iso: str,
) -> int:
    """Backfill historical bars for one instrument (runs in the worker, off the
    request path). The ingestion supervisor / live stream workers also live here
    so web deploys never interrupt market data."""
    import uuid
    from datetime import datetime

    from app.core.db import get_sessionmaker
    from app.modules.market_data import ingestion
    from app.modules.market_data.providers.factory import make_provider

    provider = make_provider(source, get_settings())
    try:
        async with get_sessionmaker()() as session:
            result = await ingestion.backfill_instrument(
                session,
                instrument_id=uuid.UUID(instrument_id),
                source=source,
                provider=provider,
                source_symbol=source_symbol,
                start=datetime.fromisoformat(start_iso),
                end=datetime.fromisoformat(end_iso),
            )
        return result.bars_written
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            await close()


async def poll_quotes(_ctx: dict[str, Any]) -> int:
    """Cron: fetch latest closed bars for active instruments and publish them
    to Redis for live WS fan-out (crypto always; equities during market hours)."""
    from app.core.db import get_sessionmaker
    from app.core.redis import get_redis_client
    from app.modules.market_data.streaming import poll_and_publish

    async with get_sessionmaker()() as session:
        return await poll_and_publish(session, get_redis_client(), get_settings())


async def run_paper_sessions(_ctx: dict[str, Any]) -> int:
    """Cron: advance every running paper session by re-running its strategy over
    the session window against the latest bars."""
    from app.core.db import get_sessionmaker
    from app.modules.trading.repository import all_running_sessions
    from app.modules.trading.service import PaperService

    async with get_sessionmaker()() as session:
        sessions = await all_running_sessions(session)
        for paper in sessions:
            # Isolate each session (B1): run_session commits its own alert rows before
            # emailing, so one owner's failure can't roll back or block another's.
            try:
                await PaperService(session, paper.owner_id).run_session(paper)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("run_paper_session_failed", session_id=str(paper.id))
    return len(sessions)


async def _on_startup(_ctx: dict[str, Any]) -> None:
    configure_logging()
    logger.info("worker_startup")


async def _on_shutdown(_ctx: dict[str, Any]) -> None:
    logger.info("worker_shutdown")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat, ingest_backfill]
    on_startup = staticmethod(_on_startup)
    on_shutdown = staticmethod(_on_shutdown)
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Poll quotes at :00/:30; advance paper sessions at :15/:45 (offset).
    cron_jobs: ClassVar[list[Any]] = [
        cron(poll_quotes, second={0, 30}),  # type: ignore[arg-type]
        cron(run_paper_sessions, second={15, 45}),  # type: ignore[arg-type]
    ]
