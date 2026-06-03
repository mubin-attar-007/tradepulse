"""Performance + risk metrics from the equity curve and trades.

Equity is converted to float here — these are display/analytics numbers, not
money accounting (which stays Decimal in the engine)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.modules.backtesting.types import EquityPoint, Trade

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def compute_metrics(
    equity_curve: Sequence[EquityPoint], trades: Sequence[Trade], timeframe: str
) -> dict[str, float]:
    base = {
        "total_return": 0.0,
        "cagr": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "num_trades": float(len(trades)),
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "avg_trade_return": 0.0,
    }
    if len(equity_curve) < 2:
        return base

    equity = np.array([float(p.equity) for p in equity_curve])
    returns = np.diff(equity) / equity[:-1]
    ppy = (365 * 24 * 60) / _TF_MINUTES.get(timeframe, 1)

    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    downside = returns[returns < 0]
    dstd = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0

    cummax = np.maximum.accumulate(equity)
    base["max_drawdown"] = float(np.min(equity / cummax - 1.0))
    base["total_return"] = float(equity[-1] / equity[0] - 1.0)
    base["sharpe"] = (mean / std) * math.sqrt(ppy) if std > 0 else 0.0
    base["sortino"] = (mean / dstd) * math.sqrt(ppy) if dstd > 0 else 0.0

    ratio = float(equity[-1] / equity[0])
    if ratio > 0 and len(returns) > 0:
        # log/expm1 raises a catchable OverflowError (unlike float ** which warns
        # and returns inf); CAGR annualized from intraday data can overflow.
        try:
            base["cagr"] = math.expm1(math.log(ratio) * ppy / len(returns))
        except (OverflowError, ValueError):
            base["cagr"] = 0.0

    if trades:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        base["win_rate"] = len(wins) / len(trades)
        gross_win = float(sum(t.pnl for t in wins))
        gross_loss = abs(float(sum(t.pnl for t in losses)))
        base["profit_factor"] = gross_win / gross_loss if gross_loss > 0 else gross_win
        base["avg_trade_return"] = float(np.mean([t.return_pct for t in trades]))

    return {k: round(v, 6) for k, v in base.items()}
