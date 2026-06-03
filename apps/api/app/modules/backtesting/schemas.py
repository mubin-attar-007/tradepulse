"""Backtest API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CreateBacktestRequest(BaseModel):
    strategy_id: uuid.UUID
    start: datetime
    end: datetime


class BacktestSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    symbol: str
    timeframe: str
    status: str
    start_ts: datetime
    end_ts: datetime
    created_at: datetime


class BacktestOut(BacktestSummaryOut):
    strategy_version: int
    result: dict[str, Any] | None
    error: str | None
