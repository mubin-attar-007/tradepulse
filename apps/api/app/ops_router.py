"""Internal cron tick — a worker replacement for free PaaS hosts (Render/Koyeb)
that don't offer an always-on background process.

An external scheduler (e.g. cron-job.org) calls POST /internal/tick?key=<secret>
every few minutes; it does exactly what the ARQ worker crons do — poll the latest
closed bars and publish them, then advance every running paper session. On a real
VM the ARQ worker handles this and this endpoint simply stays disabled.

Disabled (404) unless ``TICK_SECRET`` is set, so it's never an open endpoint.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["ops"])
logger = get_logger("ops")


@router.post("/internal/tick", include_in_schema=False)
async def tick(key: str = Query(default="")) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.tick_secret
    # 404 (not 403) so the endpoint is indistinguishable from "not found" when
    # disabled or probed with a wrong key. Constant-time compare avoids timing leaks.
    if not secret or not hmac.compare_digest(key, secret):
        raise HTTPException(status_code=404)

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
