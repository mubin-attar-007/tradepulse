"""Paper-trading API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.types import Money


class DeployRequest(BaseModel):
    strategy_id: uuid.UUID


class PaperSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version: int
    symbol: str
    timeframe: str
    status: str
    initial_cash: Money
    session_start: datetime
    last_run_at: datetime | None
    snapshot: dict[str, Any] | None
