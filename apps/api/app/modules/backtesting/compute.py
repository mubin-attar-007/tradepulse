"""Point-in-time signal evaluation over pre-computed indicator arrays.

The indicator math itself lives in :mod:`app.modules.indicators` (a primitive shared
with the chart API and the ML feature store); this module owns only the part that is
genuinely a backtesting concern: evaluating a :class:`Condition` tree at a single
CLOSED bar index ``i``.

``build_arrays`` / ``compute_indicators`` are re-exported so the engine and the older
call sites keep one import site.
"""

from __future__ import annotations

import math

from app.modules.indicators.compute import (
    PriceArrays,
    build_arrays,
    compute_indicators,
    operand_key,
)
from app.modules.strategies.spec import Comparison, Condition, Group, Operand

__all__ = [
    "PriceArrays",
    "build_arrays",
    "compute_indicators",
    "evaluate",
]


def _operand_value(op: Operand, arrays: PriceArrays, i: int) -> float:
    if op.kind == "const":
        base = float(op.value or 0.0)
    else:
        series = arrays.get(operand_key(op.kind, field=op.field, ref=op.ref, output=op.output))
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
    """Evaluate ``condition`` at CLOSED bar ``i`` (reads only indices <= i)."""
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
