"""Paper-session repositories."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import OwnedRepository
from app.modules.trading.models import PaperSession


class PaperSessionRepository(OwnedRepository[PaperSession]):
    model = PaperSession

    async def list_for_owner(self) -> Sequence[PaperSession]:
        result = await self.session.execute(self._owned().order_by(PaperSession.created_at.desc()))
        return result.scalars().all()


async def all_running_sessions(session: AsyncSession) -> Sequence[PaperSession]:
    """Cross-owner — used by the worker cron (not request-scoped)."""
    result = await session.execute(select(PaperSession).where(PaperSession.status == "running"))
    return result.scalars().all()
