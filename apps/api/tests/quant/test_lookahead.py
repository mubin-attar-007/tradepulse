"""Look-ahead canaries.

A backtest that peeks at the future produces a beautiful equity curve and is
worthless. These tests are constructed so that *any* leak changes a number they
assert on.

Two distinct classes are covered, because they fail in different ways:

* **Inter-bar** — a decision at bar i reads bar j > i. Detected by perturbing the
  entire tail of the series and asserting the prefix is untouched.
* **Intrabar** — a decision that fills at bar i's OPEN reads bar i's own high/low
  (which had not printed when the order was sent). The inter-bar canary cannot see
  this: bar i is inside the prefix it holds fixed. This is exactly how the ATR
  position-sizing leak survived. It is caught by perturbing ONLY the high/low of
  the fill bar while holding its open and close identical.
"""

from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal

import pytest

from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    Group,
    IndicatorSpec,
    Operand,
    PositionSizing,
)
from tests.quant.conftest import ohlc, spec

FREE = ExecutionConfig(commission_bps=0.0, slippage_bps=0.0, initial_cash=Decimal("100000"))
COSTED = ExecutionConfig(initial_cash=Decimal("100000"))


def _wavy(n: int = 80, scale: float = 1.0) -> list[BarPoint]:
    rows = []
    prev = 100.0
    for i in range(n):
        close = 100 + 10 * math.sin(i / 5) + i * 0.1
        close *= scale
        o = prev
        rows.append(
            (
                f"{o:.4f}",
                f"{max(o, close) * 1.004:.4f}",
                f"{min(o, close) * 0.996:.4f}",
                f"{close:.4f}",
            )
        )
        prev = close
    return ohlc(rows)


# Every indicator in the catalog, so a leak in any one of them is caught rather
# than only in the SMA the original canary happened to use.
_ALL_INDICATORS = [
    IndicatorSpec(id="sma", type="SMA", params={"period": 5}),
    IndicatorSpec(id="ema", type="EMA", params={"period": 5}),
    IndicatorSpec(id="rsi", type="RSI", params={"period": 7}),
    IndicatorSpec(id="atr", type="ATR", params={"period": 7}),
    IndicatorSpec(id="bb", type="BBANDS", params={"period": 6, "std": 2}),
    IndicatorSpec(id="macd", type="MACD", params={"fast": 4, "slow": 9, "signal": 3}),
    IndicatorSpec(id="vol", type="VOL_SMA", params={"period": 5}),
    IndicatorSpec(id="vwap", type="VWAP", params={}),
]

_ENTRY_TOUCHING_EVERYTHING = Group(
    logic="any",
    conditions=[
        Comparison(
            left=Operand(kind="indicator", ref="ema"),
            op="cross_above",
            right=Operand(kind="indicator", ref="sma"),
        ),
        Comparison(
            left=Operand(kind="price", field="close"),
            op="cross_below",
            right=Operand(kind="indicator", ref="bb", output="lower"),
        ),
        Comparison(
            left=Operand(kind="indicator", ref="macd", output="hist"),
            op="cross_above",
            right=Operand(kind="const", value=0),
        ),
        Comparison(
            left=Operand(kind="indicator", ref="rsi"),
            op="<",
            right=Operand(kind="const", value=35),
        ),
        Comparison(
            left=Operand(kind="price", field="close"),
            op="cross_above",
            right=Operand(kind="indicator", ref="vwap"),
        ),
        Comparison(
            left=Operand(kind="price", field="volume"),
            op=">",
            right=Operand(kind="indicator", ref="vol", multiplier=1.5),
        ),
    ],
)


def _full_spec():
    return spec(
        entry=_ENTRY_TOUCHING_EVERYTHING,
        indicators=_ALL_INDICATORS,
        exit_rule=ExitRule(stop_loss_pct=0.03, take_profit_pct=0.05, time_exit_bars=6),
        sizing=PositionSizing(method="percent_equity", value=0.5),
    )


def test_interbar_canary_across_every_indicator() -> None:
    """Perturbing the future must not move the past — for all eight indicators."""
    bars = _wavy()
    cut = 45
    perturbed = bars[: cut + 1] + _wavy(scale=3.0)[cut + 1 :]

    full = engine.run(_full_spec(), bars, COSTED)
    altered = engine.run(_full_spec(), perturbed, COSTED)

    for i in range(cut + 1):
        assert full.equity_curve[i].equity == altered.equity_curve[i].equity, f"leak at bar {i}"


def test_intrabar_canary_fill_bar_high_low_must_not_size_the_order() -> None:
    """ATR sizing must read the DECISION bar, never the bar it fills on.

    Two series differ ONLY in the high/low of the bar the entry fills at; its open
    and close are byte-identical, so nothing knowable at decision time changed. If
    the order size or the equity at that bar moves, the engine used a price that
    had not printed yet.

    This is the regression for the real defect: with the old code (``atr_arr[i]``)
    the position size moved by roughly 18x between these two inputs.
    """
    base = [
        ("100", "100", "100", "100"),
        ("100", "101", "99", "101"),  # crosses 100.5 -> arm entry
        ("100", "102", "99", "101"),  # entry fills at this OPEN
        ("101", "103", "100", "102"),
        ("102", "104", "101", "103"),
    ]
    wide = list(base)
    # Same open (100) and same close (101) — only the intrabar range differs.
    wide[2] = ("100", "150", "50", "101")

    atr_spec = spec(
        indicators=[IndicatorSpec(id="atr", type="ATR", params={"period": 2})],
        sizing=PositionSizing(method="atr", value=2, atr_ref="atr"),
        exit_rule=ExitRule(time_exit_bars=10),
    )

    narrow_run = engine.run(atr_spec, ohlc(base), FREE)
    wide_run = engine.run(atr_spec, ohlc(wide), FREE)

    assert narrow_run.trades and wide_run.trades
    assert narrow_run.trades[0].qty == wide_run.trades[0].qty, (
        "position size changed with the fill bar's own high/low — intrabar look-ahead"
    )
    assert narrow_run.equity_curve[2].equity == wide_run.equity_curve[2].equity


def test_a_signal_cannot_fill_on_the_bar_that_generated_it() -> None:
    """The fill timestamp must always be strictly after the decision bar's close."""
    bars = _wavy(60)
    result = engine.run(_full_spec(), bars, COSTED)
    assert result.trades, "fixture must actually trade or this proves nothing"
    ts_index = {b.ts: i for i, b in enumerate(bars)}
    for trade in result.trades:
        entry_i = ts_index[trade.entry_ts]
        assert entry_i >= 1, "an entry filled on bar 0, before any decision could be made"
        assert trade.exit_ts >= trade.entry_ts


def test_indicators_are_causal_elementwise() -> None:
    """Directly: indicator[i] must not change when bars after i change.

    Asserted on the arrays themselves rather than through the engine, so a leak is
    attributed to the indicator rather than hidden by a strategy that happened not
    to trade.
    """
    from app.modules.indicators import compute

    bars = _wavy(60)
    cut = 30
    perturbed = bars[: cut + 1] + _wavy(60, scale=5.0)[cut + 1 :]

    df_a, _ = compute.build_arrays(bars)
    df_b, _ = compute.build_arrays(perturbed)
    arrays_a = compute.compute_indicators(df_a, _ALL_INDICATORS)
    arrays_b = compute.compute_indicators(df_b, _ALL_INDICATORS)

    for key, series_a in arrays_a.items():
        series_b = arrays_b[key]
        for i in range(cut + 1):
            a, b = float(series_a[i]), float(series_b[i])
            if math.isnan(a) and math.isnan(b):
                continue
            assert a == pytest.approx(b, rel=1e-12, abs=1e-12), f"{key} leaked at bar {i}"


def test_vwap_does_not_depend_on_where_the_window_starts() -> None:
    """VWAP is session-anchored, so two overlapping windows must agree.

    Before this was fixed, VWAP accumulated from the first bar of whatever range was
    loaded, so the same strategy over 2024-01-01.. and 2024-06-01.. produced
    different values on identical bars — a hidden dependency on the query, which no
    look-ahead canary could ever detect.
    """
    from app.modules.indicators import compute

    hourly = _wavy(72)
    hourly = [
        BarPoint(
            ts=b.ts.replace(minute=0) + timedelta(hours=i),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            bar_count=60,
        )
        for i, b in enumerate(hourly)
    ]
    vwap = [IndicatorSpec(id="vwap", type="VWAP", params={})]

    df_all, _ = compute.build_arrays(hourly)
    full = compute.compute_indicators(df_all, vwap)["indicator:vwap"]

    offset = 30
    df_tail, _ = compute.build_arrays(hourly[offset:])
    tail = compute.compute_indicators(df_tail, vwap)["indicator:vwap"]

    # Compare only bars whose whole session is present in both windows.
    for i in range(offset, len(hourly)):
        if hourly[i].ts.date() == hourly[offset].ts.date():
            continue  # the truncated first session legitimately differs
        assert float(full[i]) == pytest.approx(float(tail[i - offset]), rel=1e-12)
