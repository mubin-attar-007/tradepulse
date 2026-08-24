"""Metric definitions checked against series with known answers.

Each test pins one definition. Between them they encode the three disciplines the
metrics module exists to enforce: calendar-aware annualization, sample-size gating,
and "undefined is not zero".
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.backtesting import metrics as m
from app.modules.backtesting.types import EquityPoint, Trade

BASE = datetime(2024, 1, 2, tzinfo=UTC)


def curve(values: list[float], *, step: timedelta = timedelta(days=1)) -> list[EquityPoint]:
    return [EquityPoint(ts=BASE + i * step, equity=Decimal(str(v))) for i, v in enumerate(values)]


def trade(pnl: float, *, ret: float = 0.0, bars: int = 1, commission: float = 0.0) -> Trade:
    return Trade(
        entry_ts=BASE,
        exit_ts=BASE + timedelta(minutes=bars),
        side="long",
        qty=Decimal("1"),
        entry_price=Decimal("100"),
        exit_price=Decimal("100") + Decimal(str(pnl)),
        pnl=Decimal(str(pnl)),
        return_pct=ret,
        bars_held=bars,
        exit_reason="target",
        commission=Decimal(str(commission)),
    )


# --- periods per year --------------------------------------------------------


def test_periods_per_year_is_calendar_aware() -> None:
    """The whole point of the calendar argument: crypto and equities differ.

    Getting this wrong inflated an hourly equity Sharpe by ~2.3x and an hourly CAGR
    exponent by ~5x, on numbers that were rendered to two decimal places.
    """
    assert m.periods_per_year("1d", "24x7") == 365.0
    assert m.periods_per_year("1d", "XNYS") == 252.0
    assert m.periods_per_year("1h", "24x7") == pytest.approx(365 * 24)
    assert m.periods_per_year("1h", "XNYS") == pytest.approx(252 * 6.5)
    assert m.periods_per_year("1m", "XNYS") == pytest.approx(252 * 390)
    # An equity's annualization factor must always be the smaller of the two.
    assert m.periods_per_year("1h", "XNYS") < m.periods_per_year("1h", "24x7")


# --- descriptive statistics --------------------------------------------------


def test_total_return_and_max_drawdown() -> None:
    values = [100.0, 120.0, 90.0, 110.0]
    out = m.compute_metrics(curve(values), [], "1d")
    assert out["total_return"] == pytest.approx(0.10)
    # Deepest point 90 against a running peak of 120 -> -25%.
    assert out["max_drawdown"] == pytest.approx(-0.25)


def test_drawdown_duration_and_recovery() -> None:
    # Peak at index 1, underwater for indices 2-4, new high at index 5.
    values = [100.0, 120.0, 110.0, 90.0, 115.0, 125.0]
    out = m.compute_metrics(curve(values), [], "1d")
    assert out["longest_drawdown_bars"] == 3
    # Trough at index 3; a new high is reached 2 bars later.
    assert out["recovery_bars"] == 2


def test_recovery_is_none_when_the_curve_never_recovers() -> None:
    out = m.compute_metrics(curve([100.0, 120.0, 80.0, 85.0]), [], "1d")
    assert out["recovery_bars"] is None


def test_a_flat_curve_has_no_drawdown_and_no_return() -> None:
    out = m.compute_metrics(curve([100.0] * 40), [], "1d")
    assert out["total_return"] == 0.0
    assert out["max_drawdown"] == 0.0
    # Zero variance means Sharpe is undefined, not zero.
    assert out["sharpe"] is None


# --- sample-size gating ------------------------------------------------------


def test_sharpe_is_withheld_on_a_tiny_sample() -> None:
    """Six bars cannot support an annualized risk-adjusted return.

    The previous implementation reported 14820.83 for a smooth five-point curve, and
    the same curve scored 562410.91 merely by relabelling the timeframe from 1d to
    1m. Withholding it is the honest answer.
    """
    out = m.compute_metrics(curve([100.0, 101.0, 102.0, 103.0, 104.0]), [trade(1.0)], "1d")
    assert out["sharpe"] is None
    assert out["sortino"] is None
    notes = m.sample_size_notes(out)
    assert any("Sharpe" in n for n in notes)


def test_sharpe_is_reported_once_the_sample_is_large_enough() -> None:
    values = [100.0 * (1.001**i) + (1.5 if i % 3 == 0 else -0.7) for i in range(80)]
    trades = [trade(10.0, ret=0.01) for _ in range(6)]
    out = m.compute_metrics(curve(values), trades, "1d")
    assert out["sharpe"] is not None
    assert out["sortino"] is not None
    assert m.sample_size_notes(out) == [] or all(
        "Sharpe" not in n for n in m.sample_size_notes(out)
    )


def test_cagr_is_withheld_below_the_span_floor() -> None:
    """Annualizing a two-month window extrapolates six times beyond the evidence."""
    short = curve([100.0 + i for i in range(60)])  # 59 days
    out = m.compute_metrics(short, [trade(1.0) for _ in range(6)], "1d")
    assert out["cagr"] is None
    assert out["calmar"] is None
    assert any("CAGR" in n for n in m.sample_size_notes(out))


def test_cagr_uses_wall_clock_time() -> None:
    """A doubling over exactly one year is a 100% CAGR, whatever the bar count.

    Deriving it from elapsed time rather than from a bars-per-year constant handles
    weekends, holidays and half-days exactly instead of approximately.
    """
    days = 365
    values = [100.0 * (2 ** (i / days)) for i in range(days + 1)]
    out = m.compute_metrics(curve(values), [trade(1.0) for _ in range(6)], "1d")
    assert out["cagr"] == pytest.approx(1.0, rel=1e-3)


# --- undefined is not zero ---------------------------------------------------


def test_profit_factor_is_undefined_without_a_losing_trade() -> None:
    """The old branch returned the gross dollar profit here.

    Two wins of $500 and $700 with no losses reported a "profit factor" of 1200.0 —
    a dollar amount rendered as a ratio, on a public, crawlable page.
    """
    values = [100.0 + i for i in range(60)]
    trades = [trade(500.0, ret=0.05), trade(700.0, ret=0.07)] + [
        trade(100.0, ret=0.01) for _ in range(4)
    ]
    out = m.compute_metrics(curve(values), trades, "1d")
    assert out["profit_factor"] is None
    assert any("Profit factor" in n for n in m.sample_size_notes(out))


def test_profit_factor_is_the_ratio_when_there_are_losses() -> None:
    values = [100.0 + i * 0.5 for i in range(60)]
    trades = [trade(300.0, ret=0.03), trade(-100.0, ret=-0.01)] + [
        trade(50.0, ret=0.005) for _ in range(4)
    ]
    out = m.compute_metrics(curve(values), trades, "1d")
    # gross win 300 + 200 = 500, gross loss 100 -> 5.0
    assert out["profit_factor"] == pytest.approx(5.0)


def test_sortino_uses_downside_deviation_not_the_spread_of_losses() -> None:
    """A steady drip of identical small losses has near-zero spread but real
    downside risk.

    Under the old definition (standard deviation of the negative returns about their
    own mean) the denominator collapsed toward zero and Sortino exploded. Under the
    correct definition the denominator is the size of the shortfalls, so a losing
    strategy scores negative and finite.
    """
    values = [100.0]
    for i in range(60):
        values.append(values[-1] * (1.02 if i % 4 == 0 else 0.995))
    out = m.compute_metrics(curve(values), [trade(1.0) for _ in range(6)], "1d")
    assert out["sortino"] is not None
    assert math.isfinite(out["sortino"])


def test_downside_deviation_matches_its_definition() -> None:
    import numpy as np

    returns = np.array([0.02, -0.01, 0.03, -0.04, 0.0])
    expected = math.sqrt(((0.01**2) + (0.04**2)) / 5)
    assert m._downside_deviation(returns) == pytest.approx(expected)


# --- trade statistics --------------------------------------------------------


def test_trade_statistics() -> None:
    values = [100.0 + i * 0.5 for i in range(60)]
    trades = [
        trade(100.0, ret=0.10, bars=4),
        trade(-50.0, ret=-0.05, bars=2),
        trade(20.0, ret=0.02, bars=6),
        trade(-10.0, ret=-0.01, bars=3),
        trade(40.0, ret=0.04, bars=5),
    ]
    out = m.compute_metrics(curve(values), trades, "1d")
    assert out["num_trades"] == 5
    assert out["win_rate"] == pytest.approx(3 / 5)
    assert out["expectancy"] == pytest.approx((100 - 50 + 20 - 10 + 40) / 5)
    assert out["avg_trade_return"] == pytest.approx((0.10 - 0.05 + 0.02 - 0.01 + 0.04) / 5)
    assert out["median_trade_return"] == pytest.approx(0.02)
    assert out["avg_holding_bars"] == pytest.approx((4 + 2 + 6 + 3 + 5) / 5)


def test_exposure_is_bounded() -> None:
    values = [100.0 + i for i in range(20)]
    trades = [trade(1.0, bars=50) for _ in range(5)]  # deliberately over-long
    out = m.compute_metrics(curve(values), trades, "1d")
    assert out["exposure"] is not None
    assert 0.0 <= out["exposure"] <= 1.0


def test_empty_and_degenerate_inputs_do_not_raise() -> None:
    assert m.compute_metrics([], [], "1d")["num_trades"] == 0
    assert m.compute_metrics(curve([100.0]), [], "1d")["total_return"] == 0.0
    # A zero equity point would divide by zero; the guard must return the base dict.
    assert m.compute_metrics(curve([0.0, 100.0]), [], "1d")["total_return"] == 0.0
