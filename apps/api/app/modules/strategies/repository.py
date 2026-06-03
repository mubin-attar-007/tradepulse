"""Owner-scoped strategy repositories + version helpers."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import OwnedRepository
from app.modules.strategies.models import Strategy, StrategyVersion


class StrategyRepository(OwnedRepository[Strategy]):
    model = Strategy


class StrategyVersionRepository(OwnedRepository[StrategyVersion]):
    model = StrategyVersion

    async def latest(self, strategy_id: uuid.UUID) -> StrategyVersion | None:
        return await self.session.scalar(
            self._owned()
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        )

    async def for_strategy(self, strategy_id: uuid.UUID) -> Sequence[StrategyVersion]:
        result = await self.session.execute(
            self._owned()
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
        )
        return result.scalars().all()

    async def by_version(self, strategy_id: uuid.UUID, version: int) -> StrategyVersion | None:
        return await self.session.scalar(
            self._owned().where(
                StrategyVersion.strategy_id == strategy_id, StrategyVersion.version == version
            )
        )


async def list_strategies(session: AsyncSession, owner_id: uuid.UUID) -> Sequence[Strategy]:
    result = await session.execute(
        select(Strategy).where(Strategy.owner_id == owner_id).order_by(Strategy.created_at.desc())
    )
    return result.scalars().all()
