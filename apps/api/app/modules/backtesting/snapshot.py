"""Serialize a BacktestResult to a JSON-safe dict (money as strings, invariant #2).

Shared by stored backtests and paper sessions. Equity curve / trades are capped
to keep the JSONB row bounded (the cap is logged, never silent)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.modules.backtesting.types import BacktestResult

logger = get_logger("backtesting")

_MAX_EQUITY_POINTS = 5000
_MAX_TRADES = 500


def result_to_dict(result: BacktestResult, *, as_of: datetime | None = None) -> dict[str, Any]:
    if len(result.equity_curve) > _MAX_EQUITY_POINTS:
        logger.info(
            "equity_curve_truncated", total=len(result.equity_curve), kept=_MAX_EQUITY_POINTS
        )
    if len(result.trades) > _MAX_TRADES:
        logger.info("trades_truncated", total=len(result.trades), kept=_MAX_TRADES)

    payload: dict[str, Any] = {
        "initial_cash": str(result.initial_cash),
        "final_equity": str(result.final_equity),
        "open_position": result.open_position,
        "num_trades": len(result.trades),
        "total_commission": str(result.total_commission),
        "metrics": result.metrics,
        "bars": result.bars,
        "spec_hash": result.spec_hash,
        "engine_version": result.engine_version,
        "data_fingerprint": result.data_fingerprint,
        "risk_events": [
            {"ts": e.ts.isoformat(), "kind": e.kind, "detail": e.detail} for e in result.risk_events
        ],
        "trades": [
            {
                "entry_ts": t.entry_ts.isoformat(),
                "exit_ts": t.exit_ts.isoformat(),
                "side": t.side,
                "qty": str(t.qty),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "pnl": str(t.pnl),
                "return_pct": t.return_pct,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades[-_MAX_TRADES:]
        ],
        "equity_curve": [
            {"ts": p.ts.isoformat(), "equity": str(p.equity)}
            for p in result.equity_curve[-_MAX_EQUITY_POINTS:]
        ],
    }
    if as_of is not None:
        payload["as_of"] = as_of.isoformat()
    return payload
