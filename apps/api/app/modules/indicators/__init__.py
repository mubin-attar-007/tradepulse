"""Indicator primitives: the closed catalog and its causal computation.

This is a LOW-level module (below strategies, market_data, and backtesting) because
an indicator is a primitive, not a backtesting concern: the chart API, the strategy
DSL, the backtest engine and the robustness lab all need the *same* numbers (a
future feature store would too, but none exists today). Owning them here is what
lets every one of those surfaces read identical values without any upward import.
"""

from app.modules.indicators.catalog import (
    INDICATOR_OUTPUTS,
    INDICATOR_PARAMS,
    IndicatorSpec,
    IndicatorType,
    PriceField,
    outputs_for,
    warmup_bars,
)
from app.modules.indicators.compute import (
    PriceArrays,
    build_arrays,
    compute_indicators,
    operand_key,
)

__all__ = [
    "INDICATOR_OUTPUTS",
    "INDICATOR_PARAMS",
    "IndicatorSpec",
    "IndicatorType",
    "PriceArrays",
    "PriceField",
    "build_arrays",
    "compute_indicators",
    "operand_key",
    "outputs_for",
    "warmup_bars",
]
