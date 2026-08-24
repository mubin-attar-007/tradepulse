"""Performance and risk metrics.

Three disciplines separate this from a naive metrics block:

1. **Annualization is calendar-aware.** A US equity trades ~252 sessions of 390
   minutes; crypto trades 24/7. Annualizing hourly equity bars at 8,760 periods per
   year is right for BTC and ~5x too large for AAPL. ``periods_per_year`` therefore
   takes the instrument's trading calendar, and CAGR is derived from elapsed
   WALL-CLOCK time (the equity curve carries timestamps) so holidays and weekends
   are handled exactly rather than approximated.

2. **Extrapolating statistics are gated on sample size.** A Sharpe ratio computed
   from six bars is not a small number with wide error bars — it is noise with a
   decimal point, and it looked authoritative enough on the old surface to be
   rendered to two decimal places. Anything that annualizes or extrapolates
   (Sharpe, Sortino, CAGR, Calmar) returns ``None`` below a documented floor and the
   caller renders "n/a" with the reason. Purely descriptive statistics (total
   return, drawdown, win rate, trade counts) are always reported: they are facts
   about the run, not claims about the future.

3. **Undefined is not zero.** Sortino with no losing observations, profit factor
   with no losing trades, and Sharpe with zero variance are UNDEFINED. Returning
   ``0.0`` reads as "no risk-adjusted return"; returning the gross dollar profit (as
   the previous profit-factor branch did) is worse still — it printed $1,200 of
   winnings as a ratio of 1200.0.

Equity is converted to float here — these are display/analytics numbers, not money
accounting (which stays ``Decimal`` in the engine).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.modules.backtesting.types import EquityPoint, Trade

METRICS_VERSION = "2.0.0"

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

# Trading-calendar shape. XNYS: 252 sessions/yr of 390 regular-session minutes.
# 24x7: every minute of every day.
_SESSIONS_PER_YEAR = {"XNYS": 252.0, "24x7": 365.0}
_SESSION_MINUTES = {"XNYS": 390.0, "24x7": 1440.0}

# --- Sample-size floors for extrapolating statistics -------------------------
# Deliberately conservative and stated in the API response so a caller can explain
# an "n/a" instead of silently hiding a metric.
MIN_RETURNS_FOR_RATIO = 30  # Sharpe / Sortino
MIN_TRADES_FOR_RATIO = 5  # ...and enough trades for the curve to mean anything
MIN_DAYS_FOR_ANNUALIZED = 180.0  # CAGR / Calmar: below half a year, annualizing lies

_YEAR_SECONDS = 365.25 * 24 * 3600


def periods_per_year(timeframe: str, calendar: str = "24x7") -> float:
    """Bars per year for ``timeframe`` on ``calendar``.

    Used only to annualize per-bar return statistics (Sharpe/Sortino). CAGR does
    NOT use this — it uses wall-clock elapsed time, which is exact.
    """
    sessions = _SESSIONS_PER_YEAR.get(calendar, 365.0)
    session_minutes = _SESSION_MINUTES.get(calendar, 1440.0)
    minutes = _TF_MINUTES.get(timeframe, 1)
    if minutes >= 1440:  # daily or coarser: one bar per session
        return sessions
    return sessions * (session_minutes / minutes)


def _downside_deviation(returns: np.ndarray, target: float = 0.0) -> float:
    """Root-mean-square of shortfall below ``target``, over ALL observations.

    This is the standard definition. The previous implementation took the standard
    deviation of the negative returns about *their own mean*, which measures how
    varied the losses were rather than how large they were — a strategy that loses
    a steady 0.5% every day scored a near-infinite Sortino under it.
    """
    if returns.size == 0:
        return 0.0
    shortfall = np.minimum(returns - target, 0.0)
    return float(math.sqrt(float(np.mean(shortfall**2))))


def compute_metrics(
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[Trade],
    timeframe: str,
    *,
    calendar: str = "24x7",
    risk_free_rate: float = 0.0,
) -> dict[str, float | None]:
    """Metrics for one run. ``None`` means undefined or below the sample floor.

    ``risk_free_rate`` is an ANNUAL rate; it is de-annualized to the bar frequency
    before being subtracted. It defaults to 0 and that default is stated wherever
    a Sharpe ratio is displayed.
    """
    metrics: dict[str, float | None] = {
        "total_return": 0.0,
        "cagr": None,
        "sharpe": None,
        "sortino": None,
        "calmar": None,
        "max_drawdown": 0.0,
        "longest_drawdown_bars": 0.0,
        "recovery_bars": None,
        "num_trades": float(len(trades)),
        "win_rate": None,
        "profit_factor": None,
        "expectancy": None,
        "avg_trade_return": None,
        "median_trade_return": None,
        "avg_holding_bars": None,
        "exposure": None,
        "turnover": None,
        "total_commission": None,
        "num_returns": 0.0,
        "span_days": 0.0,
    }
    if len(equity_curve) < 2:
        return metrics

    equity = np.array([float(p.equity) for p in equity_curve])
    if np.any(equity[:-1] == 0):
        return metrics
    returns = np.diff(equity) / equity[:-1]
    ppy = periods_per_year(timeframe, calendar)

    span_seconds = (equity_curve[-1].ts - equity_curve[0].ts).total_seconds()
    span_days = span_seconds / 86400.0
    metrics["num_returns"] = float(returns.size)
    metrics["span_days"] = round(span_days, 4)

    # --- Descriptive: always reported --------------------------------------
    cummax = np.maximum.accumulate(equity)
    drawdown = equity / cummax - 1.0
    metrics["max_drawdown"] = float(np.min(drawdown))
    metrics["total_return"] = float(equity[-1] / equity[0] - 1.0)

    underwater = drawdown < 0
    longest, current = 0, 0
    for flag in underwater:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    metrics["longest_drawdown_bars"] = float(longest)

    # Bars from the deepest trough back to a new high (None if never recovered).
    trough = int(np.argmin(drawdown))
    peak_value = float(cummax[trough])
    recovery = np.nonzero(equity[trough:] >= peak_value)[0]
    metrics["recovery_bars"] = float(recovery[0]) if recovery.size else None

    # --- Extrapolating: gated on sample size --------------------------------
    enough_returns = returns.size >= MIN_RETURNS_FOR_RATIO and len(trades) >= MIN_TRADES_FOR_RATIO
    if enough_returns:
        rf_per_bar = risk_free_rate / ppy if ppy > 0 else 0.0
        excess = returns - rf_per_bar
        std = float(np.std(excess, ddof=1))
        if std > 0:
            metrics["sharpe"] = float(np.mean(excess) / std * math.sqrt(ppy))
        dd = _downside_deviation(excess)
        if dd > 0:
            metrics["sortino"] = float(np.mean(excess) / dd * math.sqrt(ppy))

    if span_days >= MIN_DAYS_FOR_ANNUALIZED and equity[0] > 0 and equity[-1] > 0:
        years = span_seconds / _YEAR_SECONDS
        if years > 0:
            try:
                cagr = math.expm1(math.log(float(equity[-1] / equity[0])) / years)
            except (OverflowError, ValueError):
                cagr = None
            metrics["cagr"] = cagr
            max_dd = metrics["max_drawdown"] or 0.0
            if cagr is not None and max_dd < 0:
                metrics["calmar"] = float(cagr / abs(max_dd))

    # --- Trade statistics ----------------------------------------------------
    if trades:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        metrics["win_rate"] = len(wins) / len(trades)
        gross_win = float(sum(t.pnl for t in wins))
        gross_loss = abs(float(sum(t.pnl for t in losses)))
        # Undefined without a losing trade — NOT the dollar amount of the winnings.
        metrics["profit_factor"] = gross_win / gross_loss if gross_loss > 0 else None
        pnls = np.array([float(t.pnl) for t in trades])
        rets = np.array([t.return_pct for t in trades])
        metrics["expectancy"] = float(np.mean(pnls))
        metrics["avg_trade_return"] = float(np.mean(rets))
        metrics["median_trade_return"] = float(np.median(rets))
        metrics["avg_holding_bars"] = float(np.mean([t.bars_held for t in trades]))
        metrics["total_commission"] = float(sum(t.commission for t in trades))

        # Exposure: share of bars holding a position. Turnover: traded notional per
        # unit of starting equity (a round trip of the full account is 2.0).
        held = sum(max(t.bars_held, 0) for t in trades)
        bars_total = len(equity_curve)
        metrics["exposure"] = min(float(held) / bars_total, 1.0) if bars_total else None
        notional = float(sum(t.qty * t.entry_price + t.qty * t.exit_price for t in trades))
        metrics["turnover"] = notional / float(equity[0]) if equity[0] > 0 else None

    return {k: (round(v, 8) if isinstance(v, float) else v) for k, v in metrics.items()}


def sample_size_notes(metrics: dict[str, float | None]) -> list[str]:
    """Human-readable reasons a gated metric came back ``None``.

    Surfaced on the result so the UI can explain "n/a" instead of hiding the row —
    the absence of a Sharpe ratio is itself information about the run.
    """
    notes: list[str] = []
    returns = metrics.get("num_returns") or 0
    trades = metrics.get("num_trades") or 0
    span = metrics.get("span_days") or 0
    if returns < MIN_RETURNS_FOR_RATIO or trades < MIN_TRADES_FOR_RATIO:
        notes.append(
            f"Sharpe/Sortino not reported: needs at least {MIN_RETURNS_FOR_RATIO} return "
            f"observations and {MIN_TRADES_FOR_RATIO} trades (this run has "
            f"{int(returns)} and {int(trades)})."
        )
    if span < MIN_DAYS_FOR_ANNUALIZED:
        notes.append(
            f"CAGR/Calmar not reported: annualizing a {span:.1f}-day window extrapolates "
            f"far beyond the evidence (floor is {MIN_DAYS_FOR_ANNUALIZED:.0f} days)."
        )
    if metrics.get("profit_factor") is None and trades:
        notes.append("Profit factor undefined: the run has no losing trade to divide by.")
    return notes
