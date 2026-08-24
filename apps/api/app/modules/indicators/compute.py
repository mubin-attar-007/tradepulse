"""Causal indicator computation.

Every value at index ``i`` depends only on bars ``0..i``. That is the property the
look-ahead canary test exercises: perturbing a bar ``j > i`` cannot change
``indicator[i]``. Warm-up periods emit NaN rather than a fabricated number, and the
consumers (chart API, engine, feature store) all render or skip those NaNs
explicitly instead of forward-filling them.

Indicator math runs in float (numpy/pandas) for speed; money accounting stays
``Decimal`` in the engine. The two never mix: an indicator value is only ever
compared against another indicator/price/constant, never added to cash.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from app.modules.indicators.catalog import IndicatorSpec

# Operand-key -> value array. Keys are ``price:<field>``, ``indicator:<id>`` for
# single-output indicators, and ``indicator:<id>:<output>`` for multi-output ones.
PriceArrays = dict[str, np.ndarray]


@runtime_checkable
class Bar(Protocol):
    """Structural contract for a bar.

    Deliberately structural (not an import of ``market_data.BarPoint``) so this
    module stays below market_data in the layering and can be reused by the
    robustness lab — and by anything later, such as a feature store — without
    dragging in persistence types.
    """

    @property
    def ts(self) -> object: ...
    @property
    def open(self) -> object: ...
    @property
    def high(self) -> object: ...
    @property
    def low(self) -> object: ...
    @property
    def close(self) -> object: ...
    @property
    def volume(self) -> object: ...


def build_arrays(bars: Sequence[Bar]) -> tuple[pd.DataFrame, PriceArrays]:
    """Bars -> (float DataFrame, price operand arrays).

    ``ts`` is carried on the frame (not exposed as an operand) because
    session-anchored indicators such as VWAP need to know where a trading day
    begins; without it VWAP silently becomes a function of the query window.
    """
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime([b.ts for b in bars], utc=True),
            "open": [float(b.open) for b in bars],  # type: ignore[arg-type]
            "high": [float(b.high) for b in bars],  # type: ignore[arg-type]
            "low": [float(b.low) for b in bars],  # type: ignore[arg-type]
            "close": [float(b.close) for b in bars],  # type: ignore[arg-type]
            "volume": [float(b.volume) for b in bars],  # type: ignore[arg-type]
        }
    )
    arrays: PriceArrays = {
        f"price:{c}": df[c].to_numpy() for c in ("open", "high", "low", "close", "volume")
    }
    return df, arrays


# Exchange calendar -> IANA zone used to decide where a trading SESSION begins.
_CALENDAR_TZ = {"XNYS": "America/New_York"}


def session_key(ts: pd.Series, calendar: str) -> pd.Series:
    """Session identity per bar, for indicators that reset each trading day.

    For an exchange calendar the session is the LOCAL trading date (a US session
    runs 09:30-16:00 ET, entirely inside one ET date, even though it straddles two
    UTC dates in the evening for some venues). For 24x7 there is no session break,
    so the UTC date is used as a stable, documented daily anchor.
    """
    tz = _CALENDAR_TZ.get(calendar)
    local = ts.dt.tz_convert(tz) if tz else ts
    return local.dt.date


def _wilder_rma(values: np.ndarray, period: int, start: int) -> np.ndarray:
    """Wilder's running moving average: SMA seed, then recursive smoothing.

    The previous implementation used ``ewm(alpha=1/period, adjust=False)``, which
    seeds from the FIRST observation rather than from the mean of the first
    ``period`` observations. That is not Wilder's method and not what TA-Lib,
    TradingView, or any charting package a user compares against computes: measured
    on a random walk it put RSI(14) about 8 points off at the first usable bar and
    still ~3 points off 15 bars later. For a threshold rule like ``RSI < 30`` that
    is the difference between a trade and no trade, and the same bias fed ATR-based
    position sizing.
    """
    out = np.full(values.shape, np.nan)
    first = start + period - 1
    if values.size <= first:
        return out
    seed = float(np.mean(values[start : start + period]))
    out[first] = seed
    prev = seed
    for i in range(first + 1, values.size):
        prev = (prev * (period - 1) + float(values[i])) / period
        out[i] = prev
    return out


def _rsi(close: pd.Series, period: int) -> np.ndarray:
    delta = close.diff().to_numpy()
    gain = np.where(np.isnan(delta), np.nan, np.maximum(delta, 0.0))
    loss = np.where(np.isnan(delta), np.nan, np.maximum(-delta, 0.0))
    # Deltas are valid from index 1, so Wilder's seed spans indices 1..period.
    avg_gain = _wilder_rma(gain, period, start=1)
    avg_loss = _wilder_rma(loss, period, start=1)

    rsi = np.full(close.shape, np.nan)
    valid = ~np.isnan(avg_gain) & ~np.isnan(avg_loss)
    # Zero average loss is not "undefined" — it is a period with no down moves, and
    # RSI is 100 by definition. The old code produced NaN here, and because a NaN
    # comparison is False, a momentum rule such as ``RSI > 70`` could never fire
    # during the strongest uptrends: a direction-dependent blind spot in exactly the
    # regime the rule was written for. Symmetrically, no up moves is RSI 0.
    no_loss = valid & (avg_loss == 0)
    no_gain = valid & (avg_gain == 0) & (avg_loss > 0)
    normal = valid & (avg_loss > 0) & (avg_gain > 0)
    rsi[no_loss] = 100.0
    rsi[no_gain] = 0.0
    rs = avg_gain[normal] / avg_loss[normal]
    rsi[normal] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _atr(df: pd.DataFrame, period: int) -> np.ndarray:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # TR is defined from bar 0 (true range degenerates to high-low without a prior
    # close), so Wilder's seed spans indices 0..period-1 — matching TA-Lib.
    return _wilder_rma(tr.to_numpy(), period, start=0)


def compute_indicators(
    df: pd.DataFrame, indicators: Sequence[IndicatorSpec], *, calendar: str = "24x7"
) -> PriceArrays:
    """Return a map of operand-key -> value array for every requested indicator.

    ``calendar`` decides where a session begins for session-anchored indicators.
    """
    out: PriceArrays = {}
    close = df["close"]
    for ind in indicators:
        p = ind.params
        if ind.type == "EMA":
            out[f"indicator:{ind.id}"] = (
                close.ewm(span=int(p["period"]), adjust=False, min_periods=int(p["period"]))
                .mean()
                .to_numpy()
            )
        elif ind.type == "SMA":
            out[f"indicator:{ind.id}"] = close.rolling(int(p["period"])).mean().to_numpy()
        elif ind.type == "RSI":
            out[f"indicator:{ind.id}"] = _rsi(close, int(p["period"]))
        elif ind.type == "ATR":
            out[f"indicator:{ind.id}"] = _atr(df, int(p["period"]))
        elif ind.type == "VOL_SMA":
            out[f"indicator:{ind.id}"] = df["volume"].rolling(int(p["period"])).mean().to_numpy()
        elif ind.type == "VWAP":
            # SESSION-anchored. Anchoring to the first bar of the loaded window
            # instead (the previous behaviour) makes VWAP a function of the query
            # range: the same spec over 2024-01-01.. and 2024-06-01.. produced
            # different values on identical bars, so two runs of one strategy were
            # not comparable. That is not look-ahead, so no canary could catch it —
            # it is a hidden window dependency, which is arguably worse.
            typical = (df["high"] + df["low"] + df["close"]) / 3
            session = session_key(df["ts"], calendar)
            cum_pv = (typical * df["volume"]).groupby(session).cumsum()
            cum_v = df["volume"].groupby(session).cumsum()
            vwap = (cum_pv / cum_v.replace(0.0, np.nan)).to_numpy()
            out[f"indicator:{ind.id}"] = vwap
        elif ind.type == "BBANDS":
            period, std = int(p["period"]), float(p["std"])
            mid = close.rolling(period).mean()
            dev = close.rolling(period).std(ddof=0)
            out[f"indicator:{ind.id}:middle"] = mid.to_numpy()
            out[f"indicator:{ind.id}:upper"] = (mid + std * dev).to_numpy()
            out[f"indicator:{ind.id}:lower"] = (mid - std * dev).to_numpy()
        elif ind.type == "MACD":
            fast_p, slow_p, signal_p = int(p["fast"]), int(p["slow"]), int(p["signal"])
            # min_periods so MACD shows honest null warm-up gaps like SMA/RSI/BBANDS
            # instead of emitting finite values from bar 0. The MACD line warms up
            # over the slow EMA; the signal EMA then warms up over the (already-gapped)
            # MACD line — its own min_periods counts only non-NaN MACD inputs, so pass
            # signal_p here (NOT slow+signal) to avoid double-counting the slow warm-up.
            fast = close.ewm(span=fast_p, adjust=False, min_periods=fast_p).mean()
            slow = close.ewm(span=slow_p, adjust=False, min_periods=slow_p).mean()
            macd = fast - slow
            signal = macd.ewm(span=signal_p, adjust=False, min_periods=signal_p).mean()
            out[f"indicator:{ind.id}:macd"] = macd.to_numpy()
            out[f"indicator:{ind.id}:signal"] = signal.to_numpy()
            out[f"indicator:{ind.id}:hist"] = (macd - signal).to_numpy()
    return out


def operand_key(
    kind: str, *, field: str | None = None, ref: str | None = None, output: str | None = None
) -> str:
    """Canonical array key for an operand (shared by the engine and the chart API)."""
    if kind == "price":
        return f"price:{field}"
    if kind == "indicator":
        return f"indicator:{ref}" + (f":{output}" if output and output != "value" else "")
    return "const"
