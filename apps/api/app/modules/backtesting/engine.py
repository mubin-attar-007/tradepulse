"""The event-driven backtest engine (long-only MVP).

Discipline that makes it honest:
  * decisions are made on a CLOSED bar i (reading causal indicators at i);
  * market orders fill on the NEXT bar's OPEN (no peeking at the signal bar's close);
  * stop/target/trailing are intrabar (gap-aware: a gap-through fills at the open);
  * risk limits are ENFORCED (position clamp, daily-loss halt, consecutive-loss
    kill-switch) — not merely tracked.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from app.modules.backtesting import compute
from app.modules.backtesting.metrics import compute_metrics
from app.modules.backtesting.types import (
    BacktestResult,
    EquityPoint,
    ExecutionConfig,
    RiskEvent,
    Trade,
)
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import ENGINE_VERSION, ExitRule, PositionSizing, StrategySpec

_D0 = Decimal("0")


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _size(
    sizing: PositionSizing,
    equity: Decimal,
    fill: Decimal,
    stop_pct: float | None,
    atr: float | None,
) -> Decimal:
    value = Decimal(str(sizing.value))
    if sizing.method == "fixed_units":
        return value
    if sizing.method == "percent_equity":
        return (equity * value) / fill
    if sizing.method == "risk_per_trade":
        if stop_pct:
            stop_dist = fill * Decimal(str(stop_pct))
            if stop_dist > 0:
                return (equity * value) / stop_dist
        return (equity * value) / fill
    if sizing.method == "atr":
        if atr and atr > 0:
            stop_dist = Decimal(str(atr)) * value
            if stop_dist > 0:
                return (equity * Decimal("0.01")) / stop_dist
        return (equity * Decimal("0.01")) / fill
    return _D0


def slippage_fraction(config: ExecutionConfig) -> Decimal:
    """Adverse slippage as a Decimal fraction (0 when frictionless)."""
    return _D0 if config.frictionless else Decimal(str(config.slippage_bps)) / Decimal(10000)


def entry_fill(reference_price: Decimal, slip: Decimal) -> Decimal:
    """Long entry fill = reference price nudged up by adverse slippage.

    This is the SAME formula the engine applies to the next bar's open
    (``o * (1 + slip)``); the signal service passes the latest close as the
    reference so it never reimplements the fill math."""
    return reference_price * (Decimal(1) + slip)


def stop_from_fill(fill: Decimal, exit_rule: ExitRule) -> Decimal | None:
    """Protective stop from the fill — identical to the engine's bracket math."""
    if not exit_rule.stop_loss_pct:
        return None
    return fill * (Decimal(1) - Decimal(str(exit_rule.stop_loss_pct)))


def target_from_fill(fill: Decimal, exit_rule: ExitRule) -> Decimal | None:
    """Profit target from the fill — identical to the engine's bracket math."""
    if not exit_rule.take_profit_pct:
        return None
    return fill * (Decimal(1) + Decimal(str(exit_rule.take_profit_pct)))


def size_for_entry(
    spec: StrategySpec, equity: Decimal, fill: Decimal, atr: float | None
) -> Decimal:
    """Intended position size for a long entry at ``fill`` with ``equity`` of
    buying power — the SAME ``_size()`` the engine uses, then clamped by
    ``max_position_pct`` exactly as the engine clamps a real fill."""
    size = _size(spec.sizing, equity, fill, spec.exit.stop_loss_pct, atr)
    max_notional = equity * Decimal(str(spec.risk.max_position_pct))
    if fill > 0 and size * fill > max_notional:
        size = max_notional / fill
    return size if size > 0 else _D0


def run(
    spec: StrategySpec,
    bars: Sequence[BarPoint],
    config: ExecutionConfig,
    *,
    close_at_end: bool = True,
) -> BacktestResult:
    df, arrays = compute.build_arrays(bars)
    arrays.update(compute.compute_indicators(df, spec.indicators))

    slip = slippage_fraction(config)
    comm = _D0 if config.frictionless else Decimal(str(config.commission_bps)) / Decimal(10000)

    exit_rule = spec.exit
    atr_arr = None
    if spec.sizing.method == "atr" and spec.sizing.atr_ref:
        atr_arr = arrays.get(f"indicator:{spec.sizing.atr_ref}")
    tod_start = _to_minutes(spec.time_of_day.start) if spec.time_of_day else None
    tod_end = _to_minutes(spec.time_of_day.end) if spec.time_of_day else None

    cash = config.initial_cash
    total_commission = _D0
    equity_curve: list[EquityPoint] = []
    trades: list[Trade] = []
    risk_events: list[RiskEvent] = []

    in_pos = False
    qty = _D0
    entry_price = _D0
    entry_gross = _D0
    entry_ts = bars[0].ts
    entry_i = 0
    highest = _D0
    stop_price: Decimal | None = None
    target_price: Decimal | None = None

    pending_entry = False
    pending_exit: str | None = None  # "signal" | "time"
    consecutive_losses = 0
    halted = False  # kill-switch (consecutive losses)
    current_day: date | None = None
    day_start_equity = cash
    day_halted = False

    def sell_fill(price: Decimal) -> Decimal:
        return price * (Decimal(1) - slip)

    def close_position(exit_fill: Decimal, ts: datetime, idx: int, reason: str) -> None:
        nonlocal cash, total_commission, in_pos, qty, consecutive_losses, halted
        proceeds = qty * exit_fill
        commission = proceeds * comm
        cash += proceeds - commission
        total_commission += commission
        exit_net = proceeds - commission
        pnl = exit_net - entry_gross
        trades.append(
            Trade(
                entry_ts=entry_ts,
                exit_ts=ts,
                side="long",
                qty=qty,
                entry_price=entry_price,
                exit_price=exit_fill,
                pnl=pnl,
                return_pct=float(pnl / entry_gross) if entry_gross > 0 else 0.0,
                bars_held=idx - entry_i,
                exit_reason=reason,
                commission=commission,
            )
        )
        consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
        if (
            spec.risk.max_consecutive_losses
            and consecutive_losses >= spec.risk.max_consecutive_losses
        ):
            halted = True
            risk_events.append(
                RiskEvent(ts=ts, kind="max_consecutive_losses", detail=str(consecutive_losses))
            )
        in_pos = False
        qty = _D0

    for i, bar in enumerate(bars):
        o, h, low_, c = bar.open, bar.high, bar.low, bar.close

        day = bar.ts.date()
        if day != current_day:
            current_day = day
            day_start_equity = cash + (qty * o if in_pos else _D0)
            day_halted = False

        # 1) pending exit (signal/time) fills at this open
        if in_pos and pending_exit is not None:
            close_position(sell_fill(o), bar.ts, i, pending_exit)
            pending_exit = None

        # 2) pending entry fills at this open
        if not in_pos and pending_entry:
            pending_entry = False
            equity = cash
            fill = entry_fill(o, slip)
            atr_val = float(atr_arr[i]) if atr_arr is not None else None
            size = _size(spec.sizing, equity, fill, exit_rule.stop_loss_pct, atr_val)
            max_notional = equity * Decimal(str(spec.risk.max_position_pct))
            if size * fill > max_notional and fill > 0:
                size = max_notional / fill
                risk_events.append(
                    RiskEvent(ts=bar.ts, kind="position_clamped", detail="max_position_pct")
                )
            notional = size * fill
            commission = notional * comm
            if notional + commission > cash and fill > 0:
                size = (cash / (Decimal(1) + comm)) / fill
                notional = size * fill
                commission = notional * comm
            if size > 0:
                cash -= notional + commission
                total_commission += commission
                in_pos = True
                qty = size
                entry_price = fill
                entry_gross = notional + commission
                entry_ts = bar.ts
                entry_i = i
                highest = h
                stop_price = stop_from_fill(fill, exit_rule)
                target_price = target_from_fill(fill, exit_rule)

        # 3) intrabar bracket checks
        if in_pos:
            if exit_rule.trailing_stop_pct:
                highest = max(highest, h)
                trail = highest * (Decimal(1) - Decimal(str(exit_rule.trailing_stop_pct)))
                stop_price = trail if stop_price is None else max(stop_price, trail)
            if stop_price is not None and low_ <= stop_price:
                fill = o if o <= stop_price else stop_price  # gap-through fills at open
                close_position(sell_fill(fill), bar.ts, i, "stop")
            elif target_price is not None and h >= target_price:
                fill = o if o >= target_price else target_price
                close_position(sell_fill(fill), bar.ts, i, "target")

        # 4) time exit -> next open
        if in_pos and exit_rule.time_exit_bars and (i - entry_i) >= exit_rule.time_exit_bars:
            pending_exit = "time"

        # 5) mark-to-market at close
        equity = cash + (qty * c if in_pos else _D0)
        equity_curve.append(EquityPoint(ts=bar.ts, equity=equity))

        # 6) daily-loss kill-switch
        if (
            spec.risk.max_daily_loss_pct
            and not day_halted
            and equity - day_start_equity
            < -(day_start_equity * Decimal(str(spec.risk.max_daily_loss_pct)))
        ):
            day_halted = True
            risk_events.append(RiskEvent(ts=bar.ts, kind="max_daily_loss", detail="halted for day"))

        # 7) decisions at close for the NEXT bar
        if i < len(bars) - 1:
            if not in_pos and not halted and not day_halted:
                in_window = True
                if tod_start is not None and tod_end is not None:
                    minute = bar.ts.hour * 60 + bar.ts.minute
                    in_window = tod_start <= minute < tod_end
                if in_window and compute.evaluate(spec.entry_long, arrays, i):
                    pending_entry = True
            elif (
                in_pos
                and pending_exit is None
                and exit_rule.exit_conditions is not None
                and compute.evaluate(exit_rule.exit_conditions, arrays, i)
            ):
                pending_exit = "signal"

    # Backtest flattens at the end for clean accounting; paper trading
    # (close_at_end=False) keeps the position open and reports it.
    open_position: dict[str, object] | None = None
    if in_pos:
        if close_at_end:
            close_position(sell_fill(bars[-1].close), bars[-1].ts, len(bars) - 1, "eod")
            equity_curve[-1] = EquityPoint(ts=bars[-1].ts, equity=cash)
        else:
            open_position = {
                "qty": str(qty),
                "entry_price": str(entry_price),
                "entry_ts": entry_ts.isoformat(),
                "bars_held": len(bars) - 1 - entry_i,
            }

    final_equity = equity_curve[-1].equity if equity_curve else config.initial_cash
    metrics = compute_metrics(equity_curve, trades, spec.timeframe)
    return BacktestResult(
        initial_cash=config.initial_cash,
        final_equity=final_equity,
        equity_curve=equity_curve,
        trades=trades,
        risk_events=risk_events,
        metrics=metrics,
        total_commission=total_commission,
        bars=len(bars),
        open_position=open_position,
        engine_version=ENGINE_VERSION,
    )
