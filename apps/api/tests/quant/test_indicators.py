"""Indicator alignment, warm-up, and seeding parity.

The indicator catalog declares a warm-up length for every entry; these tests assert
the implementation actually matches that declaration, so the validator and the
engine cannot drift apart from the documentation.

Wilder-seeded values are checked against an independent recurrence written out
here, because the difference between Wilder's method and a plain recursive EWM is
several RSI points for dozens of bars after warm-up — enough to flip a ``RSI < 30``
rule between trading and not trading, and enough to make the platform's numbers
disagree with any chart a user compares them against.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.modules.indicators import catalog, compute
from app.modules.market_data.repository import BarPoint

BASE = datetime(2024, 1, 2, tzinfo=UTC)


def _bars(closes: list[float], *, step: timedelta = timedelta(minutes=1)) -> list[BarPoint]:
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(
            BarPoint(
                ts=BASE + i * step,
                open=Decimal(str(round(o, 6))),
                high=Decimal(str(round(max(o, c) * 1.002, 6))),
                low=Decimal(str(round(min(o, c) * 0.998, 6))),
                close=Decimal(str(round(c, 6))),
                volume=Decimal("1000"),
                bar_count=1,
            )
        )
        prev = c
    return out


def _series(bars, spec, key: str | None = None, calendar: str = "24x7") -> np.ndarray:
    df, _ = compute.build_arrays(bars)
    arrays = compute.compute_indicators(df, [spec], calendar=calendar)
    return arrays[key or f"indicator:{spec.id}"]


def _first_valid(arr: np.ndarray) -> int:
    for i, v in enumerate(arr):
        if not math.isnan(float(v)):
            return i
    return len(arr)


_WALK = [100 + 8 * math.sin(i / 3.5) + i * 0.05 for i in range(90)]


@pytest.mark.parametrize(
    ("ind_type", "params", "output"),
    [
        ("SMA", {"period": 10}, None),
        ("EMA", {"period": 10}, None),
        ("RSI", {"period": 14}, None),
        ("ATR", {"period": 14}, None),
        ("VOL_SMA", {"period": 10}, None),
        ("BBANDS", {"period": 20, "std": 2}, "middle"),
        ("MACD", {"fast": 12, "slow": 26, "signal": 9}, "signal"),
        ("VWAP", {}, None),
    ],
)
def test_declared_warmup_matches_the_implementation(ind_type, params, output) -> None:  # type: ignore[no-untyped-def]
    """catalog.warmup_bars() must equal the true index of the first real value.

    If these disagree, the spec validator either rejects viable strategies or lets
    through ones that silently produce no signals.
    """
    spec = catalog.IndicatorSpec(id="x", type=ind_type, params=params)
    key = f"indicator:x:{output}" if output else "indicator:x"
    arr = _series(_bars(_WALK), spec, key)
    assert _first_valid(arr) == catalog.warmup_bars(ind_type, params)


def test_sma_is_exactly_the_mean_of_the_window() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    arr = _series(_bars(closes), catalog.IndicatorSpec(id="s", type="SMA", params={"period": 3}))
    assert math.isnan(float(arr[0])) and math.isnan(float(arr[1]))
    assert float(arr[2]) == pytest.approx(2.0)  # (1+2+3)/3
    assert float(arr[5]) == pytest.approx(5.0)  # (4+5+6)/3


def test_ema_matches_the_recurrence_from_its_own_seed() -> None:
    """EMA_t = alpha*close_t + (1-alpha)*EMA_{t-1}, alpha = 2/(n+1)."""
    closes = _WALK
    period = 10
    arr = _series(
        _bars(closes), catalog.IndicatorSpec(id="e", type="EMA", params={"period": period})
    )
    alpha = 2.0 / (period + 1)
    start = _first_valid(arr)
    expected = float(arr[start])
    for i in range(start + 1, len(closes)):
        expected = alpha * float(round(closes[i], 6)) + (1 - alpha) * expected
        assert float(arr[i]) == pytest.approx(expected, rel=1e-9)


def test_rsi_uses_wilder_seeding() -> None:
    """RSI must match an independent Wilder implementation, not a plain EWM.

    Reference: seed avg gain/loss with the MEAN of the first `period` deltas, then
    smooth recursively with (prev*(n-1) + x)/n.
    """
    period = 14
    closes = [round(c, 6) for c in _WALK]
    arr = _series(
        _bars(closes), catalog.IndicatorSpec(id="r", type="RSI", params={"period": period})
    )

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period

    def rsi_of(g: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        if g == 0:
            return 0.0
        return 100.0 - 100.0 / (1.0 + g / loss)

    assert float(arr[period]) == pytest.approx(rsi_of(avg_g, avg_l), rel=1e-9)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
        avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        assert float(arr[i]) == pytest.approx(rsi_of(avg_g, avg_l), rel=1e-9)


def test_rsi_is_100_not_nan_when_there_are_no_losses() -> None:
    """A monotonic rise is RSI 100 by definition.

    The old implementation divided by a zeroed average loss and produced NaN, and
    because every comparison against NaN is False, a rule like ``RSI > 70`` could
    never fire during the strongest uptrend — a silent, direction-dependent blind
    spot in exactly the regime such a rule targets.
    """
    rising = [100.0 + i for i in range(40)]
    arr = _series(_bars(rising), catalog.IndicatorSpec(id="r", type="RSI", params={"period": 14}))
    tail = arr[14:]
    assert not np.isnan(tail).any()
    assert float(tail[-1]) == pytest.approx(100.0)


def test_rsi_is_0_when_there_are_no_gains() -> None:
    falling = [200.0 - i for i in range(40)]
    arr = _series(_bars(falling), catalog.IndicatorSpec(id="r", type="RSI", params={"period": 14}))
    assert float(arr[-1]) == pytest.approx(0.0)


def test_rsi_stays_in_range() -> None:
    arr = _series(_bars(_WALK), catalog.IndicatorSpec(id="r", type="RSI", params={"period": 14}))
    finite = arr[~np.isnan(arr)]
    assert finite.size > 0
    assert float(finite.min()) >= 0.0 and float(finite.max()) <= 100.0


def test_atr_uses_wilder_seeding_over_true_range() -> None:
    period = 5
    bars = _bars(_WALK[:40])
    arr = _series(bars, catalog.IndicatorSpec(id="a", type="ATR", params={"period": period}))

    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    closes = [float(b.close) for b in bars]
    tr = [highs[0] - lows[0]]
    for i in range(1, len(bars)):
        tr.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )
    expected = sum(tr[:period]) / period
    assert float(arr[period - 1]) == pytest.approx(expected, rel=1e-9)
    for i in range(period, len(bars)):
        expected = (expected * (period - 1) + tr[i]) / period
        assert float(arr[i]) == pytest.approx(expected, rel=1e-9)


def test_bollinger_bands_are_symmetric_about_the_middle() -> None:
    spec = catalog.IndicatorSpec(id="b", type="BBANDS", params={"period": 20, "std": 2})
    bars = _bars(_WALK)
    df, _ = compute.build_arrays(bars)
    arrays = compute.compute_indicators(df, [spec])
    upper = arrays["indicator:b:upper"]
    middle = arrays["indicator:b:middle"]
    lower = arrays["indicator:b:lower"]
    for i in range(20, len(bars)):
        assert float(upper[i]) - float(middle[i]) == pytest.approx(
            float(middle[i]) - float(lower[i]), rel=1e-9
        )
        assert float(lower[i]) <= float(middle[i]) <= float(upper[i])


def test_macd_histogram_is_the_line_minus_its_signal() -> None:
    spec = catalog.IndicatorSpec(id="m", type="MACD", params={"fast": 12, "slow": 26, "signal": 9})
    df, _ = compute.build_arrays(_bars(_WALK))
    arrays = compute.compute_indicators(df, [spec])
    macd, signal, hist = (
        arrays["indicator:m:macd"],
        arrays["indicator:m:signal"],
        arrays["indicator:m:hist"],
    )
    for i in range(len(macd)):
        if math.isnan(float(hist[i])):
            continue
        assert float(hist[i]) == pytest.approx(float(macd[i]) - float(signal[i]), rel=1e-9)


def test_vwap_resets_each_session() -> None:
    """A new session must restart the accumulation, so the first bar of a session
    has VWAP equal to that bar's own typical price."""
    hourly = _bars([100 + i for i in range(48)], step=timedelta(hours=1))
    arr = _series(hourly, catalog.IndicatorSpec(id="v", type="VWAP", params={}))
    typical_first = (float(hourly[0].high) + float(hourly[0].low) + float(hourly[0].close)) / 3
    assert float(arr[0]) == pytest.approx(typical_first, rel=1e-9)
    # Bar 24 opens the second UTC day.
    typical_day2 = (float(hourly[24].high) + float(hourly[24].low) + float(hourly[24].close)) / 3
    assert float(arr[24]) == pytest.approx(typical_day2, rel=1e-9)


def test_vwap_session_boundary_follows_the_exchange_calendar() -> None:
    """On XNYS the session boundary is the New York date, not the UTC date.

    A bar at 23:00 UTC is 18:00 the SAME New York day, so it must stay in that
    session rather than starting a new one.
    """
    hourly = _bars([100 + i for i in range(30)], step=timedelta(hours=1))
    utc_anchored = _series(hourly, catalog.IndicatorSpec(id="v", type="VWAP", params={}))
    ny_anchored = _series(
        hourly, catalog.IndicatorSpec(id="v", type="VWAP", params={}), calendar="XNYS"
    )
    assert not np.allclose(utc_anchored[20:28], ny_anchored[20:28], equal_nan=True), (
        "XNYS anchoring produced identical values to UTC anchoring"
    )


def test_nan_warmup_is_never_backfilled() -> None:
    """Warm-up gaps stay NaN. Forward-filling them would invent values the market
    never produced and quietly enable trades before an indicator is defined."""
    arr = _series(_bars(_WALK), catalog.IndicatorSpec(id="s", type="SMA", params={"period": 30}))
    assert np.isnan(arr[:29]).all()
    assert not math.isnan(float(arr[29]))
