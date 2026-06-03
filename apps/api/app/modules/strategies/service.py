"""Strategy create/versioning logic. Versions are immutable; an unchanged spec
(same spec_hash as the latest version) is a no-op dedup."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.strategies.models import Strategy, StrategyVersion
from app.modules.strategies.repository import (
    StrategyRepository,
    StrategyVersionRepository,
)
from app.modules.strategies.spec import ENGINE_VERSION, StrategySpec


class StrategyService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.strategies = StrategyRepository(session, owner_id)
        self.versions = StrategyVersionRepository(session, owner_id)

    async def create(self, spec: StrategySpec) -> tuple[Strategy, StrategyVersion]:
        strategy = Strategy(name=spec.name, status="draft", latest_version=0)
        await self.strategies.add(strategy)
        version = await self._add_version(strategy, spec)
        return strategy, version

    async def save_version(self, strategy_id: uuid.UUID, spec: StrategySpec) -> StrategyVersion:
        strategy = await self.strategies.get(strategy_id)
        if strategy is None:
            raise NotFoundError()
        latest = await self.versions.latest(strategy_id)
        if latest is not None and latest.spec_hash == spec.spec_hash():
            return latest  # unchanged — dedup
        return await self._add_version(strategy, spec)

    async def _add_version(self, strategy: Strategy, spec: StrategySpec) -> StrategyVersion:
        next_version = strategy.latest_version + 1
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=next_version,
            spec=spec.model_dump(mode="json"),
            spec_hash=spec.spec_hash(),
            engine_version=ENGINE_VERSION,
        )
        await self.versions.add(version)
        strategy.latest_version = next_version
        strategy.name = spec.name
        await self.session.flush()
        return version
