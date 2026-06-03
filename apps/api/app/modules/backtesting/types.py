"""Backtest domain types. Money/quantity are Decimal (invariant #2); indicator
math runs in float."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    commission_bps: float = 2.0  # per side, 2 bps = 0.02%
    slippage_bps: float = 1.0  # adverse, applied to fills
    initial_cash: Decimal = Decimal("100000")
    frictionless: bool = False  # TEST-ONLY: zero commission + slippage (loudly flagged)


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
    metrics: dict[str, float]
    total_commission: Decimal
    bars: int
    spec_hash: str = ""
    engine_version: str = ""
    data_fingerprint: str = ""
