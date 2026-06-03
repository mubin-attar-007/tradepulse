"""ARQ worker entrypoint (``arq app.worker.WorkerSettings``).

Shares the app package with the API process. The market-data ingestion
supervisor (Phase 2) and scheduled jobs will live HERE — never in the API
lifespan — so web deploys never interrupt the live feed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("worker")


async def heartbeat(_ctx: dict[str, Any]) -> str:
    """Trivial job proving the worker path end-to-end (replaced in Phase 2)."""
    logger.info("worker_heartbeat")
    return "ok"


async def _on_startup(_ctx: dict[str, Any]) -> None:
    configure_logging()
    logger.info("worker_startup")


async def _on_shutdown(_ctx: dict[str, Any]) -> None:
    logger.info("worker_shutdown")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat]
    on_startup = staticmethod(_on_startup)
    on_shutdown = staticmethod(_on_shutdown)
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Cron jobs (market-hours-aware ingestion, gap-fill sweep) land in Phase 2.
    cron_jobs: ClassVar[list[Any]] = []
