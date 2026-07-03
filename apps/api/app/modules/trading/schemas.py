"""Paper-trading API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AlertOut(BaseModel):
    """One fired paper-trading alert (entry/exit fill or risk event)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    kind: str  # entry | exit | risk_event
    symbol: str
    detail: dict[str, Any]
    created_at: datetime


class PositionSizeRequest(BaseModel):
    """Inputs for a position-sizing computation. All money/price inputs are decimals
    sent as JSON numbers; the server returns Decimal STRINGS (invariant #2) so the
    client never does money math.

    ``stop`` is the protective-stop PRICE (used to derive risk-per-share for the
    ``risk_per_trade`` method); ``atr`` is the absolute ATR value for ``atr`` sizing.
    """

    model_config = ConfigDict(extra="forbid")

    method: Literal["fixed_units", "percent_equity", "risk_per_trade", "atr"]
    value: float = Field(gt=0)
    equity: Money = Field(gt=0)
    entry: Money = Field(gt=0)
    stop: Money | None = Field(default=None, gt=0)
    atr: float | None = Field(default=None, gt=0)


class PositionSizeOut(BaseModel):
    """Sizing GUIDANCE — never an executable order (live trading stays gated).
    All figures are Decimal strings computed server-side from the engine's math."""

    qty: Money
    notional: Money
    risk_amount: Money  # $ at risk between entry and stop (0 when no usable stop)
    pct_of_equity: Money  # notional / equity, as a fraction (e.g. "0.25" = 25%)
