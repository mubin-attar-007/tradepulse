"""The canonical StrategySpec DSL (ADR-0008) — the single source of truth shared
by the builder UI, the backtest engine, paper trading, and the AI layer.

It is declarative and non-Turing-complete: operands can only reference a CLOSED
catalog of indicators + price fields evaluated on closed bars, so look-ahead is
structurally impossible. Exit logic, position sizing, and risk limits are
MANDATORY — making the legacy's optimistic, entry-only strategy un-authorable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "0.1.0"
SPEC_VERSION: Literal["1.0"] = "1.0"

IndicatorType = Literal["EMA", "SMA", "RSI", "ATR", "BBANDS", "MACD", "VWAP", "VOL_SMA"]
PriceField = Literal["open", "high", "low", "close", "volume"]
CompareOp = Literal[">", "<", ">=", "<=", "cross_above", "cross_below"]
Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]

# Required params per indicator -> inclusive (min, max) range.
_INDICATOR_PARAMS: dict[str, dict[str, tuple[float, float]]] = {
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
_INDICATOR_OUTPUTS: dict[str, set[str]] = {
    "BBANDS": {"upper", "middle", "lower"},
    "MACD": {"macd", "signal", "hist"},
}


class IndicatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    type: IndicatorType
    params: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_params(self) -> IndicatorSpec:
        required = _INDICATOR_PARAMS[self.type]
        for name, (lo, hi) in required.items():
            if name not in self.params:
                raise ValueError(f"{self.type} requires param '{name}'")
            if not (lo <= self.params[name] <= hi):
                raise ValueError(f"{self.type}.{name} must be in [{lo}, {hi}]")
        unexpected = set(self.params) - set(required)
        if unexpected:
            raise ValueError(f"{self.type} got unexpected params {sorted(unexpected)}")
        return self


class Operand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["price", "indicator", "const"]
    field: PriceField | None = None  # kind=price
    ref: str | None = None  # kind=indicator -> indicator id
    output: str | None = None  # multi-output indicator selector
    value: float | None = None  # kind=const
    multiplier: float = 1.0  # linear transform: multiplier*X + offset
    offset: float = 0.0

    @model_validator(mode="after")
    def _validate(self) -> Operand:
        if self.kind == "price" and self.field is None:
            raise ValueError("price operand requires 'field'")
        if self.kind == "indicator" and not self.ref:
            raise ValueError("indicator operand requires 'ref'")
        if self.kind == "const" and self.value is None:
            raise ValueError("const operand requires 'value'")
        return self


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["compare"] = "compare"
    left: Operand
    op: CompareOp
    right: Operand


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["group"] = "group"
    logic: Literal["all", "any"]
    conditions: list[Condition] = Field(min_length=1)


Condition = Annotated[Comparison | Group, Field(discriminator="type")]

# Group.conditions references Condition (defined just above) — rebuild to resolve.
Group.model_rebuild()


class ExitRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stop_loss_pct: float | None = Field(default=None, gt=0, le=1)
    take_profit_pct: float | None = Field(default=None, gt=0)
    trailing_stop_pct: float | None = Field(default=None, gt=0, le=1)
    time_exit_bars: int | None = Field(default=None, gt=0)
    exit_conditions: Condition | None = None

    @model_validator(mode="after")
    def _require_one(self) -> ExitRule:
        mechanisms = [
            self.stop_loss_pct,
            self.take_profit_pct,
            self.trailing_stop_pct,
            self.time_exit_bars,
            self.exit_conditions,
        ]
        if not any(m is not None for m in mechanisms):
            raise ValueError("exit rule must define at least one exit mechanism")
        return self


class PositionSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["fixed_units", "percent_equity", "risk_per_trade", "atr"]
    value: float = Field(gt=0)
    atr_ref: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> PositionSizing:
        if self.method in ("percent_equity", "risk_per_trade") and not (0 < self.value <= 1):
            raise ValueError(f"{self.method} value must be in (0, 1]")
        if self.method == "atr" and self.atr_ref is None:
            raise ValueError("atr sizing requires 'atr_ref'")
        return self


class RiskLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_position_pct: float = Field(default=1.0, gt=0, le=1)
    max_open_positions: int = Field(default=1, ge=1)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=1)
    max_consecutive_losses: int | None = Field(default=None, ge=1)


class TimeOfDayFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: Literal["exchange", "utc"] = "exchange"


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_version: Literal["1.0"] = SPEC_VERSION
    name: str = Field(min_length=1, max_length=120)
    universe: list[str] = Field(min_length=1)
    timeframe: Timeframe
    indicators: list[IndicatorSpec] = Field(default_factory=list)
    entry_long: Condition
    entry_short: Condition | None = None
    exit: ExitRule
    sizing: PositionSizing
    risk: RiskLimits = Field(default_factory=RiskLimits)
    time_of_day: TimeOfDayFilter | None = None

    @model_validator(mode="after")
    def _validate_references(self) -> StrategySpec:
        ids = [ind.id for ind in self.indicators]
        if len(ids) != len(set(ids)):
            raise ValueError("indicator ids must be unique")
        by_id = {ind.id: ind for ind in self.indicators}

        def check_operand(op: Operand) -> None:
            if op.kind != "indicator":
                return
            indicator = by_id.get(op.ref or "")
            if indicator is None:
                raise ValueError(f"operand references unknown indicator '{op.ref}'")
            outputs = _INDICATOR_OUTPUTS.get(indicator.type)
            if outputs is not None:
                if op.output not in outputs:
                    raise ValueError(f"{indicator.type} requires output in {sorted(outputs)}")
            elif op.output not in (None, "value"):
                raise ValueError(f"{indicator.type} has no output '{op.output}'")

        def walk(condition: Condition) -> None:
            if isinstance(condition, Comparison):
                check_operand(condition.left)
                check_operand(condition.right)
            else:
                for child in condition.conditions:
                    walk(child)

        walk(self.entry_long)
        if self.entry_short is not None:
            walk(self.entry_short)
        if self.exit.exit_conditions is not None:
            walk(self.exit.exit_conditions)
        if self.sizing.method == "atr":
            atr = by_id.get(self.sizing.atr_ref or "")
            if atr is None or atr.type != "ATR":
                raise ValueError("sizing.atr_ref must reference an ATR indicator")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


def example_composite_spec() -> StrategySpec:
    """The carried-forward composite idea, re-expressed with mandatory exits,
    sizing, and risk (the things the legacy lacked)."""
    return StrategySpec(
        name="Composite EMA/BB/RSI (example)",
        universe=["BTC/USD"],
        timeframe="5m",
        indicators=[
            IndicatorSpec(id="ema_fast", type="EMA", params={"period": 20}),
            IndicatorSpec(id="ema_slow", type="EMA", params={"period": 50}),
            IndicatorSpec(id="rsi", type="RSI", params={"period": 14}),
            IndicatorSpec(id="bb", type="BBANDS", params={"period": 20, "std": 2}),
            IndicatorSpec(id="vol_avg", type="VOL_SMA", params={"period": 20}),
            IndicatorSpec(id="atr", type="ATR", params={"period": 14}),
        ],
        entry_long=Group(
            logic="all",
            conditions=[
                Comparison(
                    left=Operand(kind="indicator", ref="ema_fast"),
                    op=">",
                    right=Operand(kind="indicator", ref="ema_slow"),
                ),
                Comparison(
                    left=Operand(kind="price", field="close"),
                    op="<=",
                    right=Operand(kind="indicator", ref="bb", output="lower"),
                ),
                Comparison(
                    left=Operand(kind="indicator", ref="rsi"),
                    op="<",
                    right=Operand(kind="const", value=30),
                ),
                Comparison(
                    left=Operand(kind="price", field="volume"),
                    op=">",
                    right=Operand(kind="indicator", ref="vol_avg", multiplier=1.7),
                ),
            ],
        ),
        exit=ExitRule(stop_loss_pct=0.02, take_profit_pct=0.04, time_exit_bars=24),
        sizing=PositionSizing(method="risk_per_trade", value=0.01),
        risk=RiskLimits(max_position_pct=0.25, max_open_positions=1, max_consecutive_losses=5),
    )
