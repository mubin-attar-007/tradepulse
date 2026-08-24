"""Shared builders for the quant suite.

Deliberately hermetic: no database, no Redis, no network. Every test here runs the
engine directly over an in-memory bar list so a failure points at the engine rather
than at infrastructure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    Condition,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


def bar(
    i: int,
    o: str,
    h: str,
    low: str,
    c: str,
    volume: str = "1000",
    *,
    step: timedelta = timedelta(minutes=1),
) -> BarPoint:
    """One bar from exact decimal strings — never floats, so a fixture's arithmetic
    is exact and a golden value can be asserted to the last digit."""
    return BarPoint(
        ts=BASE + i * step,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(volume),
        bar_count=1,
    )


def ohlc(rows: list[tuple[str, str, str, str]], *, step: timedelta = timedelta(minutes=1)):
    """A bar series from (open, high, low, close) tuples."""
    return [bar(i, *row, step=step) for i, row in enumerate(rows)]


def cross_above_const(threshold: str) -> Condition:
    """close crossing UP through a constant — fires on exactly one bar, which keeps
    a fixture to a known number of trades."""
    return Comparison(
        left=Operand(kind="price", field="close"),
        op="cross_above",
        right=Operand(kind="const", value=float(threshold)),
    )


def spec(
    *,
    entry: Condition | None = None,
    exit_rule: ExitRule | None = None,
    sizing: PositionSizing | None = None,
    risk: RiskLimits | None = None,
    indicators: list[IndicatorSpec] | None = None,
    timeframe: str = "1m",
    name: str = "fixture",
) -> StrategySpec:
    return StrategySpec(
        name=name,
        universe=["X"],
        timeframe=timeframe,  # type: ignore[arg-type]
        indicators=indicators or [],
        entry_long=entry or cross_above_const("100.5"),
        exit=exit_rule or ExitRule(stop_loss_pct=0.10, take_profit_pct=0.05),
        sizing=sizing or PositionSizing(method="fixed_units", value=100),
        risk=risk or RiskLimits(max_position_pct=1.0, max_open_positions=1),
    )
