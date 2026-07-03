"""Causal indicator computation + point-in-time signal evaluation.

Indicators are computed over the full series with pandas (each value at index i
depends only on bars 0..i — causal), then the engine reads strictly at index i.
Perturbing a future bar j>i cannot change indicator[i], which is what makes the
look-ahead canary hold.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import Comparison, Condition, Group, IndicatorSpec, Operand

# Arrays the engine needs at each index.
PriceArrays = dict[str, np.ndarray]


def build_arrays(bars: Sequence[BarPoint]) -> tuple[pd.DataFrame, PriceArrays]:
    df = pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
        }
    )
    arrays: PriceArrays = {f"price:{c}": df[c].to_numpy() for c in df.columns}
    return df, arrays


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_indicators(df: pd.DataFrame, indicators: Sequence[IndicatorSpec]) -> PriceArrays:
    """Return a map of operand-key -> value array. Keys: ``indicator:<id>`` for
    single-output, ``indicator:<id>:<output>`` for multi-output."""
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
            out[f"indicator:{ind.id}"] = _rsi(close, int(p["period"])).to_numpy()
        elif ind.type == "ATR":
            out[f"indicator:{ind.id}"] = _atr(df, int(p["period"])).to_numpy()
        elif ind.type == "VOL_SMA":
            out[f"indicator:{ind.id}"] = df["volume"].rolling(int(p["period"])).mean().to_numpy()
        elif ind.type == "VWAP":
            typical = (df["high"] + df["low"] + df["close"]) / 3
            cum_v = df["volume"].cumsum()
            out[f"indicator:{ind.id}"] = ((typical * df["volume"]).cumsum() / cum_v).to_numpy()
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
            # (N3) instead of emitting finite values from bar 0. The MACD line warms up
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


def _operand_key(op: Operand) -> str:
    if op.kind == "price":
        return f"price:{op.field}"
    if op.kind == "indicator":
        return f"indicator:{op.ref}" + (
            f":{op.output}" if op.output and op.output != "value" else ""
        )
    return "const"


def _operand_value(op: Operand, arrays: PriceArrays, i: int) -> float:
    if op.kind == "const":
        base = float(op.value or 0.0)
    else:
        series = arrays.get(_operand_key(op))
        if series is None:
            return math.nan
        base = float(series[i])
    return base * op.multiplier + op.offset


def _compare(op: str, left: float, right: float, left_prev: float, right_prev: float) -> bool:
    if math.isnan(left) or math.isnan(right):
        return False
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "cross_above":
        if math.isnan(left_prev) or math.isnan(right_prev):
            return False
        return left_prev <= right_prev and left > right
    if op == "cross_below":
        if math.isnan(left_prev) or math.isnan(right_prev):
            return False
        return left_prev >= right_prev and left < right
    return False


def evaluate(condition: Condition, arrays: PriceArrays, i: int) -> bool:
    if isinstance(condition, Comparison):
        prev = i - 1
        left = _operand_value(condition.left, arrays, i)
        right = _operand_value(condition.right, arrays, i)
        left_prev = _operand_value(condition.left, arrays, prev) if prev >= 0 else math.nan
        right_prev = _operand_value(condition.right, arrays, prev) if prev >= 0 else math.nan
        return _compare(condition.op, left, right, left_prev, right_prev)
    group: Group = condition
    results = (evaluate(child, arrays, i) for child in group.conditions)
    return all(results) if group.logic == "all" else any(results)
