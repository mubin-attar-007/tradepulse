"""Differential testing against an independent reference implementation.

The reference below is written from the *specification* of the execution model, not
from the engine's code — deliberately structured differently (a simple state
machine over the bar list, no risk events, no metrics) so a shared misreading is
unlikely to cancel out. Hypothesis then drives both with random price paths,
random costs and random exit configurations, and every trade is compared
field-by-field.

Scope is the restricted class the reference covers: long-only, fixed-unit sizing,
next-bar-open fills, stop / target / time exits. That is narrow on purpose — a
reference implementation that is as complicated as the thing it checks proves
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 1, 2, tzinfo=UTC)


@dataclass
class RefTrade:
    entry_i: int
    exit_i: int
    entry_price: Decimal
    exit_price: Decimal
    qty: Decimal
    reason: str


def reference_run(
    bars: list[BarPoint],
    *,
    qty: Decimal,
    threshold: Decimal,
    stop_pct: Decimal | None,
    target_pct: Decimal | None,
    time_exit: int | None,
    slip: Decimal,
    comm: Decimal,
    cash: Decimal,
) -> tuple[list[RefTrade], Decimal]:
    """An independent long-only replay of the documented execution model.

    Entry rule: close crosses UP through ``threshold`` (previous close at or below
    it, this close above it) — the same closed-bar semantics as ``cross_above``.
    """
    trades: list[RefTrade] = []
    position: RefTrade | None = None
    pending_entry = False
    pending_exit = False
    entry_gross = Decimal(0)

    for i, b in enumerate(bars):
        # 1) a scheduled exit fills at this open
        if position is not None and pending_exit:
            fill = b.open * (Decimal(1) - slip)
            proceeds = position.qty * fill
            cash += proceeds - proceeds * comm
            position.exit_i, position.exit_price, position.reason = i, fill, "time"
            trades.append(position)
            position, pending_exit = None, False

        # 2) a scheduled entry fills at this open
        if position is None and pending_entry:
            pending_entry = False
            fill = b.open * (Decimal(1) + slip)
            notional = qty * fill
            fee = notional * comm
            if notional + fee <= cash and fill > 0:
                cash -= notional + fee
                entry_gross = notional + fee
                position = RefTrade(i, i, fill, Decimal(0), qty, "")

        # 3) brackets, checked intrabar against the levels implied by the fill
        if position is not None:
            stop = position.entry_price * (Decimal(1) - stop_pct) if stop_pct else None
            target = position.entry_price * (Decimal(1) + target_pct) if target_pct else None
            hit: tuple[Decimal, str] | None = None
            if stop is not None and b.low <= stop:
                hit = (b.open if b.open <= stop else stop, "stop")
            elif target is not None and b.high >= target:
                hit = (b.open if b.open >= target else target, "target")
            if hit is not None:
                fill = hit[0] * (Decimal(1) - slip)
                proceeds = position.qty * fill
                cash += proceeds - proceeds * comm
                position.exit_i, position.exit_price, position.reason = i, fill, hit[1]
                trades.append(position)
                position = None

        # 4) a time exit is scheduled for the next open
        if position is not None and time_exit and (i - position.entry_i) >= time_exit:
            pending_exit = True

        # 5) decide at this close for the NEXT bar
        if i < len(bars) - 1 and position is None and not pending_entry and i >= 1:
            crossed = bars[i - 1].close <= threshold < b.close
            if crossed:
                pending_entry = True

    # flatten at the last close
    if position is not None:
        fill = bars[-1].close * (Decimal(1) - slip)
        proceeds = position.qty * fill
        cash += proceeds - proceeds * comm
        position.exit_i, position.exit_price, position.reason = len(bars) - 1, fill, "eod"
        trades.append(position)

    _ = entry_gross
    return trades, cash


def _spec(
    threshold: Decimal,
    qty: Decimal,
    stop_pct: Decimal | None,
    target_pct: Decimal | None,
    time_exit: int | None,
) -> StrategySpec:
    return StrategySpec(
        name="differential",
        universe=["X"],
        timeframe="1m",
        indicators=[],
        entry_long=Comparison(
            left=Operand(kind="price", field="close"),
            op="cross_above",
            right=Operand(kind="const", value=float(threshold)),
        ),
        exit=ExitRule(
            stop_loss_pct=float(stop_pct) if stop_pct else None,
            take_profit_pct=float(target_pct) if target_pct else None,
            time_exit_bars=time_exit,
        ),
        sizing=PositionSizing(method="fixed_units", value=float(qty)),
        risk=RiskLimits(max_position_pct=1.0, max_open_positions=1),
    )


@st.composite
def price_paths(draw: st.DrawFn) -> list[BarPoint]:
    n = draw(st.integers(min_value=6, max_value=45))
    closes = draw(
        st.lists(
            st.integers(min_value=8000, max_value=12000),
            min_size=n,
            max_size=n,
        )
    )
    bars: list[BarPoint] = []
    prev = Decimal(closes[0]) / 100
    for i, raw in enumerate(closes):
        close = Decimal(raw) / 100
        o = prev
        # A real bar's range always contains its own open and close.
        high = max(o, close) + Decimal(draw(st.integers(min_value=0, max_value=150))) / 100
        low = min(o, close) - Decimal(draw(st.integers(min_value=0, max_value=150))) / 100
        bars.append(
            BarPoint(
                ts=BASE + timedelta(minutes=i),
                open=o,
                high=high,
                low=max(low, Decimal("0.01")),
                close=close,
                volume=Decimal(1000),
                bar_count=1,
            )
        )
        prev = close
    return bars


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    bars=price_paths(),
    threshold_raw=st.integers(min_value=9000, max_value=11000),
    qty_raw=st.integers(min_value=1, max_value=50),
    stop_raw=st.one_of(st.none(), st.integers(min_value=1, max_value=30)),
    target_raw=st.one_of(st.none(), st.integers(min_value=1, max_value=30)),
    time_exit=st.one_of(st.none(), st.integers(min_value=1, max_value=8)),
    comm_bps=st.sampled_from([0.0, 1.0, 2.0, 10.0]),
    slip_bps=st.sampled_from([0.0, 1.0, 5.0]),
)
def test_engine_matches_independent_reference(
    bars: list[BarPoint],
    threshold_raw: int,
    qty_raw: int,
    stop_raw: int | None,
    target_raw: int | None,
    time_exit: int | None,
    comm_bps: float,
    slip_bps: float,
) -> None:
    if stop_raw is None and target_raw is None and time_exit is None:
        time_exit = 3  # the DSL requires at least one exit mechanism

    threshold = Decimal(threshold_raw) / 100
    qty = Decimal(qty_raw)
    stop_pct = Decimal(stop_raw) / 100 if stop_raw else None
    target_pct = Decimal(target_raw) / 100 if target_raw else None

    config = ExecutionConfig(
        commission_bps=comm_bps, slippage_bps=slip_bps, initial_cash=Decimal("100000")
    )
    result = engine.run(_spec(threshold, qty, stop_pct, target_pct, time_exit), bars, config)

    ref_trades, ref_cash = reference_run(
        bars,
        qty=qty,
        threshold=threshold,
        stop_pct=stop_pct,
        target_pct=target_pct,
        time_exit=time_exit,
        slip=Decimal(str(slip_bps)) / Decimal(10000),
        comm=Decimal(str(comm_bps)) / Decimal(10000),
        cash=Decimal("100000"),
    )

    assert len(result.trades) == len(ref_trades), (
        f"trade count differs: engine {len(result.trades)} vs reference {len(ref_trades)}"
    )
    for got, expected in zip(result.trades, ref_trades, strict=True):
        assert got.qty == expected.qty
        assert got.entry_price == expected.entry_price
        assert got.exit_price == expected.exit_price
        assert got.exit_reason == expected.reason
    assert result.final_equity == ref_cash
