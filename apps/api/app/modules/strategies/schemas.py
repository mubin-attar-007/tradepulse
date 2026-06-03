"""Strategy API response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.strategies.models import Strategy, StrategyVersion
from app.modules.strategies.spec import StrategySpec


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    latest_version: int
    created_at: datetime
    updated_at: datetime


class StrategyVersionOut(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    version: int
    spec: StrategySpec
    spec_hash: str
    engine_version: str
    created_at: datetime

    @classmethod
    def from_model(cls, row: StrategyVersion) -> StrategyVersionOut:
        return cls(
            id=row.id,
            strategy_id=row.strategy_id,
            version=row.version,
            spec=StrategySpec.model_validate(row.spec),
            spec_hash=row.spec_hash,
            engine_version=row.engine_version,
            created_at=row.created_at,
        )


class StrategyDetailOut(BaseModel):
    strategy: StrategyOut
    latest: StrategyVersionOut | None

    @classmethod
    def build(cls, strategy: Strategy, version: StrategyVersion | None) -> StrategyDetailOut:
        return cls(
            strategy=StrategyOut.model_validate(strategy),
            latest=StrategyVersionOut.from_model(version) if version is not None else None,
        )
