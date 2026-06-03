"""Financial-correctness tests for the backtest engine (hermetic, no DB).

These are the crown jewels: look-ahead immunity, cash conservation, determinism,
cost-realism, and that stops actually fire.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


def _bars_from_closes(closes: list[float]) -> list[BarPoint]:
    bars: list[BarPoint] = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i > 0 else close
        high = max(open_, close) * 1.001
        low = min(open_, close) * 0.999
        bars.append(
            BarPoint(
                ts=BASE + timedelta(minutes=i),
                open=Decimal(str(round(open_, 4))),
                high=Decimal(str(round(high, 4))),
                low=Decimal(str(round(low, 4))),
                close=Decimal(str(round(close, 4))),
                volume=Decimal("100"),
            )
        )
    return bars


def _spec() -> StrategySpec:
    return StrategySpec(
        name="sma-cross",
        universe=["X"],
        timeframe="1m",
        indicators=[IndicatorSpec(id="sma", type="SMA", params={"period": 3})],
        entry_long=Comparison(
            left=Operand(kind="price", field="close"),
            op=">",
            right=Operand(kind="indicator", ref="sma"),
        ),
        exit=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05, time_exit_bars=5),
        sizing=PositionSizing(method="percent_equity", value=0.5),
        risk=RiskLimits(max_position_pct=1.0, max_open_positions=1),
    )


_WAVY = [round(100 + 10 * math.sin(i / 5) + i * 0.1, 4) for i in range(60)]


def test_engine_actually_trades() -> None:
    result = engine.run(_spec(), _bars_from_closes(_WAVY), ExecutionConfig())
    assert len(result.trades) > 0  # otherwise the other tests are vacuous


def test_lookahead_canary() -> None:
    bars = _bars_from_closes(_WAVY)
    full = engine.run(_spec(), bars, ExecutionConfig())

    cut = 35
    perturbed_tail = _bars_from_closes([c * 3 for c in _WAVY])
    perturbed = bars[: cut + 1] + perturbed_tail[cut + 1 :]
    altered = engine.run(_spec(), perturbed, ExecutionConfig())

    # Equity through bar `cut` depends only on bars 0..cut — perturbing the
    # future must not change it (decisions on closed bars, causal indicators).
    for i in range(cut + 1):
        assert full.equity_curve[i].equity == altered.equity_curve[i].equity


def test_cash_conservation() -> None:
    result = engine.run(_spec(), _bars_from_closes(_WAVY), ExecutionConfig())
    realized = sum((t.pnl for t in result.trades), Decimal("0"))
    # Conserved to sub-cent (residual is only Decimal 28-digit rounding, ~1e-22).
    assert abs((result.initial_cash + realized) - result.final_equity) < Decimal("0.000001")


def test_determinism() -> None:
    bars = _bars_from_closes(_WAVY)
    r1 = engine.run(_spec(), bars, ExecutionConfig())
    r2 = engine.run(_spec(), bars, ExecutionConfig())
    assert [p.equity for p in r1.equity_curve] == [p.equity for p in r2.equity_curve]
    assert r1.final_equity == r2.final_equity
    assert len(r1.trades) == len(r2.trades)


def test_frictionless_beats_or_matches_realistic() -> None:
    bars = _bars_from_closes(_WAVY)
    realistic = engine.run(_spec(), bars, ExecutionConfig())
    frictionless = engine.run(_spec(), bars, ExecutionConfig(frictionless=True))
    assert frictionless.total_commission == Decimal("0")
    if realistic.trades:
        assert frictionless.final_equity >= realistic.final_equity


def test_stop_loss_fires() -> None:
    # Rise to trigger an entry, then gap/crash through the 5% stop.
    closes = [100, 100, 100, 101, 102, 90, 90, 90, 90]
    result = engine.run(_spec(), _bars_from_closes(closes), ExecutionConfig())
    stops = [t for t in result.trades if t.exit_reason == "stop"]
    assert stops, "expected a stop-loss exit"
    assert stops[0].pnl < 0


def test_metrics_present_and_sane() -> None:
    result = engine.run(_spec(), _bars_from_closes(_WAVY), ExecutionConfig())
    assert {"sharpe", "max_drawdown", "total_return", "win_rate"} <= set(result.metrics)
    assert result.metrics["max_drawdown"] <= 0.0
