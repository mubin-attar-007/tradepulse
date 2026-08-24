"""The CLOSED indicator catalog.

Every indicator the platform supports is declared here with typed parameters,
inclusive parameter ranges, declared outputs, and a documented warm-up length.
Nothing is exposed merely because pandas or a third-party library can compute it:
an entry in this table is a commitment to test it, document it, and keep its
alignment causal.

`warmup_bars()` is the contract the validator and the engine both rely on — it is
the number of leading bars for which the indicator legitimately emits NaN. The
platform never back-fills a fabricated value into that gap.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IndicatorType = Literal[
    "EMA",
    "SMA",
    "RSI",
    "ATR",
    "BBANDS",
    "MACD",
    "VWAP",
    "VOL_SMA",
]

PriceField = Literal["open", "high", "low", "close", "volume"]

# Required params per indicator -> inclusive (min, max) range.
INDICATOR_PARAMS: dict[str, dict[str, tuple[float, float]]] = {
    "EMA": {"period": (1, 1000)},
    "SMA": {"period": (1, 1000)},
    "RSI": {"period": (2, 1000)},
    "ATR": {"period": (1, 1000)},
    "VWAP": {},
    "VOL_SMA": {"period": (1, 1000)},
    "BBANDS": {"period": (2, 1000), "std": (0.1, 10)},
    "MACD": {"fast": (1, 1000), "slow": (1, 1000), "signal": (1, 1000)},
}

# Multi-output indicators; everything else implicitly outputs "value".
INDICATOR_OUTPUTS: dict[str, set[str]] = {
    "BBANDS": {"upper", "middle", "lower"},
    "MACD": {"macd", "signal", "hist"},
}


def outputs_for(indicator_type: str) -> tuple[str, ...]:
    """Declared output names, in a stable order ("value" for single-output types)."""
    if indicator_type == "BBANDS":
        return ("upper", "middle", "lower")
    if indicator_type == "MACD":
        return ("macd", "signal", "hist")
    return ("value",)


class IndicatorSpec(BaseModel):
    """One catalog entry instantiated with concrete parameters."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    type: IndicatorType
    params: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_params(self) -> IndicatorSpec:
        required = INDICATOR_PARAMS[self.type]
        for name, (lo, hi) in required.items():
            if name not in self.params:
                raise ValueError(f"{self.type} requires param '{name}'")
            if not (lo <= self.params[name] <= hi):
                raise ValueError(f"{self.type}.{name} must be in [{lo}, {hi}]")
        unexpected = set(self.params) - set(required)
        if unexpected:
            raise ValueError(f"{self.type} got unexpected params {sorted(unexpected)}")
        return self

    def warmup(self) -> int:
        return warmup_bars(self.type, self.params)


def warmup_bars(indicator_type: str, params: dict[str, float]) -> int:
    """Index of the first bar at which this indicator produces a real value.

    Equivalently: the number of leading bars that legitimately yield NaN. The spec
    validator uses it to reject a strategy whose requested history cannot even warm
    up its own indicators, and the engine uses it to explain an empty result rather
    than reporting "0 trades" as though the rules simply never fired.

    These numbers are asserted against the implementation in
    ``tests/test_indicators.py`` — if a formula's seeding changes, that test fails
    rather than the two drifting apart silently.
    """
    if indicator_type in {"EMA", "SMA", "ATR", "VOL_SMA", "BBANDS"}:
        return int(params["period"]) - 1
    if indicator_type == "RSI":
        # Wilder seeds from the mean of the first `period` DELTAS, and a delta needs
        # a prior bar — so the first real value lands one bar later than an SMA's.
        return int(params["period"])
    if indicator_type == "MACD":
        # The MACD line warms up over the slow EMA; the signal EMA then warms up
        # over the already-gapped MACD line, counting only non-NaN inputs.
        return int(params["slow"]) + int(params["signal"]) - 2
    if indicator_type == "VWAP":
        # Session-anchored: defined from the first bar of each session.
        return 0
    return 0
