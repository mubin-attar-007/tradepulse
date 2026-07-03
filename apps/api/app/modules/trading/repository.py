"""Paper-session repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import OwnedRepository
from app.modules.trading.models import Alert, PaperSession


class PaperSessionRepository(OwnedRepository[PaperSession]):
    model = PaperSession

    async def list_for_owner(self) -> Sequence[PaperSession]:
        result = await self.session.execute(self._owned().order_by(PaperSession.created_at.desc()))
        return result.scalars().all()


class AlertRepository(OwnedRepository[Alert]):
    model = Alert

    async def list_for_owner(self, *, limit: int = 100) -> Sequence[Alert]:
        result = await self.session.execute(
            self._owned().order_by(Alert.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def existing_dedup_keys(self, session_id: uuid.UUID) -> set[str]:
        """Dedup handles already persisted for a session — the idempotency guard
        the snapshot-diff dispatcher checks before emitting a new Alert (the cron
        runs every ~30s, so the SAME fill/RiskEvent appears in every snapshot)."""
        result = await self.session.execute(
            select(Alert.dedup_key).where(
                Alert.owner_id == self.owner_id, Alert.session_id == session_id
            )
        )
        return set(result.scalars().all())


async def all_running_sessions(session: AsyncSession) -> Sequence[PaperSession]:
    """Cross-owner — used by the worker cron (not request-scoped)."""
    result = await session.execute(select(PaperSession).where(PaperSession.status == "running"))
    return result.scalars().all()
