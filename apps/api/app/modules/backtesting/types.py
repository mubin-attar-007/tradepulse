"""Backtest domain types. Money/quantity are Decimal (invariant #2); indicator
math runs in float."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

COST_MODEL_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Cost and execution assumptions for a run.

    Versioned and persisted with every result: a frictionless run and a costed run
    used to serialize identically, so a stored result could not be told apart from
    one produced with zero costs. ``COST_MODEL_VERSION`` changes whenever the cost
    semantics change, so old results stay interpretable.
    """

    commission_bps: float = 2.0  # per side, 2 bps = 0.02%
    slippage_bps: float = 1.0  # adverse, applied to fills
    initial_cash: Decimal = Decimal("100000")
    frictionless: bool = False  # TEST-ONLY: zero commission + slippage (loudly flagged)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe record of the assumptions, for the result artifact."""
        return {
            "cost_model_version": COST_MODEL_VERSION,
            "commission_bps": self.commission_bps,
            "slippage_bps": self.slippage_bps,
            "initial_cash": str(self.initial_cash),
            "frictionless": self.frictionless,
        }


@dataclass(frozen=True, slots=True)
class Trade:
    entry_ts: datetime
    exit_ts: datetime
    side: str  # "long"
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal  # net of commission
    return_pct: float
    bars_held: int
    exit_reason: str  # stop | target | trailing | time | signal | eod
    commission: Decimal


@dataclass(frozen=True, slots=True)
class EquityPoint:
    ts: datetime
    equity: Decimal


@dataclass(frozen=True, slots=True)
class RiskEvent:
    ts: datetime
    kind: str  # max_consecutive_losses | max_daily_loss | position_clamped
    detail: str


@dataclass(slots=True)
class BacktestResult:
    initial_cash: Decimal
    final_equity: Decimal
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    risk_events: list[RiskEvent]
    # ``None`` for a metric that is undefined (no losing trade to divide by) or
    # below its sample-size floor — never silently coerced to 0.0.
    metrics: dict[str, float | None]
    total_commission: Decimal
    bars: int
    open_position: dict[str, Any] | None = None  # set when run with close_at_end=False (paper)
    spec_hash: str = ""
    engine_version: str = ""
    data_fingerprint: str = ""
