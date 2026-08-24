"""The strategy intermediate representation.

A language model is NOT asked to produce a ``StrategySpec``. It is asked to produce
this — a small, flat, forgiving structure — and a deterministic compiler turns that
into the real spec.

Why the indirection is the right call rather than an extra layer:

* **It removes a whole class of model errors.** In the full spec, an indicator is
  declared once with an id and then referenced by that id, with an ``output``
  selector for multi-output indicators. Every one of those is a chance for a model
  to invent an id it never declared, reference a missing output, or contradict
  itself across two conditions. Here an operand simply says "EMA, period 20"; the
  compiler allocates and wires the ids, and by construction they always agree.

* **It is roughly a fifth of the tokens.** A full spec for a two-condition strategy
  is 600-800 tokens of JSON. The IR is around 120. On the local-first path that is
  the difference between a three-minute wait and a thirty-second one on CPU, which
  is the difference between a usable feature and a demo.

* **It is the same target the deterministic extractor produces**, which is what lets
  the semantic checker compare "what the user asked for" against "what the model
  produced" in one vocabulary instead of trying to diff two JSON documents.

The compiler is the only thing that writes a ``StrategySpec``, so every safety rule
in the DSL — mandatory exits, capability limits, parameter ranges — applies to
model output exactly as it applies to hand-authored input.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.indicators.catalog import INDICATOR_PARAMS, IndicatorSpec, outputs_for
from app.modules.strategies.spec import (
    Comparison,
    Condition,
    ExitRule,
    Group,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
    Timeframe,
)

IR_VERSION: Literal["1.0"] = "1.0"

IRIndicator = Literal["EMA", "SMA", "RSI", "ATR", "BBANDS", "MACD", "VWAP", "VOL_SMA"]
IROp = Literal["crosses_above", "crosses_below", "above", "below", "at_or_above", "at_or_below"]

_OP_TO_DSL = {
    "crosses_above": "cross_above",
    "crosses_below": "cross_below",
    "above": ">",
    "below": "<",
    "at_or_above": ">=",
    "at_or_below": "<=",
}


_PRICE_FIELDS = {"open", "high", "low", "close", "volume"}
# "EMA{period:20}", "EMA(20)", "EMA 20", "ema_20", "BBANDS{period:20,std:2}.lower"
_SHORTHAND = re.compile(
    r"^\s*(?:price\.)?(?P<name>[A-Za-z_]+\d*)"
    r"(?:\s*[({\[]\s*(?P<args>[^)}\]]*)\s*[)}\]])?"
    r"(?:\s*[._:]\s*(?P<output>upper|middle|lower|macd|signal|hist))?"
    r"\s*$",
    re.I,
)
_ARG = re.compile(r"(?:(?P<key>[A-Za-z_]+)\s*[:=]\s*)?(?P<value>-?\d+(?:\.\d+)?)")
# Positional args, in the order a person would write them.
_POSITIONAL: dict[str, tuple[str, ...]] = {
    "EMA": ("period",),
    "SMA": ("period",),
    "RSI": ("period",),
    "ATR": ("period",),
    "VOL_SMA": ("period",),
    "BBANDS": ("period", "std"),
    "MACD": ("fast", "slow", "signal"),
    "VWAP": (),
}
_ALIASES = {"VOLSMA": "VOL_SMA", "BB": "BBANDS", "BOLLINGER": "BBANDS", "PRICE": "close"}


def _coerce_term(value: Any) -> Any:
    """Accept the compact string forms models actually produce.

    Measured behaviour, not speculation: asked for a Term object, qwen2.5:3b
    returned ``"EMA{period:20}"`` — the very notation used in the prompt's parameter
    table. Rejecting that would be technically correct and practically useless: the
    model had the strategy exactly right and lost it on punctuation, then burned two
    slow repair rounds on the same mistake.

    Being liberal HERE is safe precisely because it is the only liberal step. The
    coerced Term is validated against the catalog like any other, and the compiler
    downstream applies the full DSL. A shorthand that does not resolve to a real
    indicator still fails — it just fails with a useful message.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value

    # A bare number is a constant.
    try:
        return {"kind": "const", "value": float(text)}
    except ValueError:
        pass

    match = _SHORTHAND.match(text)
    if match is None:
        return value
    raw_name = match.group("name").upper().replace("-", "_")
    params: dict[str, float] = {}

    # "EMA20" / "ema_20": the period is fused to the name rather than bracketed.
    inline_period: float | None = None
    trailing = re.search(r"(\d+)$", raw_name)
    if trailing and raw_name.rstrip("0123456789").rstrip("_") not in {"", "VOL"}:
        candidate = raw_name[: trailing.start()].rstrip("_")
        if _ALIASES.get(candidate, candidate) in _POSITIONAL:
            inline_period = float(trailing.group(1))
            raw_name = candidate

    name = _ALIASES.get(raw_name, raw_name)
    if name.lower() in _PRICE_FIELDS:
        return {"kind": "price", "field": name.lower()}
    if name not in _POSITIONAL:
        return value

    positional = _POSITIONAL[name]
    index = 0
    for arg in _ARG.finditer(match.group("args") or ""):
        key = arg.group("key")
        number = float(arg.group("value"))
        if key:
            params[key.lower()] = number
        elif index < len(positional):
            params[positional[index]] = number
            index += 1
    if not params and inline_period is not None and positional:
        params[positional[0]] = inline_period
    # Fill in the conventional defaults for the multi-parameter indicators rather
    # than failing on a partially-specified one.
    if name == "BBANDS":
        params.setdefault("period", 20.0)
        params.setdefault("std", 2.0)
    if name == "MACD":
        params.setdefault("fast", 12.0)
        params.setdefault("slow", 26.0)
        params.setdefault("signal", 9.0)

    term: dict[str, Any] = {"kind": "indicator", "indicator": name, "params": params}
    output = match.group("output")
    if output:
        term["output"] = output.lower()
    elif name == "BBANDS":
        term["output"] = "middle"
    elif name == "MACD":
        term["output"] = "macd"
    return term


class Term(BaseModel):
    """One side of a comparison. Exactly one of the three shapes."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["indicator", "price", "const"]
    indicator: IRIndicator | None = None
    # Free-form params keyed as the catalog names them (period, fast, slow, signal, std).
    params: dict[str, float] = Field(default_factory=dict)
    output: str | None = None  # BBANDS: upper|middle|lower; MACD: macd|signal|hist
    field: Literal["open", "high", "low", "close", "volume"] | None = None
    value: float | None = None
    # Multiplier lets "volume is 1.5x its 20-period average" stay one comparison.
    multiplier: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, value: Any) -> Any:
        return _coerce_term(value)

    @model_validator(mode="after")
    def _validate(self) -> Term:
        if self.kind == "indicator":
            if self.indicator is None:
                raise ValueError("indicator term requires 'indicator'")
            required = set(INDICATOR_PARAMS[self.indicator])
            missing = required - set(self.params)
            if missing:
                raise ValueError(f"{self.indicator} requires {sorted(missing)}")
            allowed = outputs_for(self.indicator)
            if allowed != ("value",) and (self.output or "") not in allowed:
                raise ValueError(f"{self.indicator} requires output in {list(allowed)}")
        elif self.kind == "price" and self.field is None:
            raise ValueError("price term requires 'field'")
        elif self.kind == "const" and self.value is None:
            raise ValueError("const term requires 'value'")
        return self

    def signature(self) -> str:
        """Stable identity, used by the semantic checker to compare terms."""
        if self.kind == "indicator":
            params = ",".join(f"{k}={self.params[k]:g}" for k in sorted(self.params))
            out = f":{self.output}" if self.output else ""
            mult = f"*{self.multiplier:g}" if self.multiplier != 1.0 else ""
            return f"{self.indicator}({params}){out}{mult}"
        if self.kind == "price":
            mult = f"*{self.multiplier:g}" if self.multiplier != 1.0 else ""
            return f"price.{self.field}{mult}"
        return f"const({self.value:g})"


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: Term
    op: IROp
    right: Term

    def signature(self) -> str:
        return f"{self.left.signature()} {self.op} {self.right.signature()}"


class ExitIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    time_exit_bars: int | None = None
    rules: list[Rule] = Field(default_factory=list)
    rules_logic: Literal["all", "any"] = "any"


class SizingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["fixed_units", "percent_equity", "risk_per_trade", "atr"] = "percent_equity"
    value: float = 0.1
    atr_period: int | None = None


class RiskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_position_pct: float = 1.0
    max_daily_loss_pct: float | None = None
    max_consecutive_losses: int | None = None


class StrategyIntent(BaseModel):
    """What the user asked for, in one vocabulary.

    Produced BOTH by the deterministic extractor (from the user's text) and by the
    language model (from the same text). Comparing the two is the semantic check.
    """

    model_config = ConfigDict(extra="forbid")

    ir_version: Literal["1.0"] = IR_VERSION
    name: str | None = None
    symbol: str | None = None
    timeframe: Timeframe | None = None
    entry: list[Rule] = Field(default_factory=list)
    entry_logic: Literal["all", "any"] = "all"
    exit: ExitIntent = Field(default_factory=ExitIntent)
    sizing: SizingIntent = Field(default_factory=SizingIntent)
    risk: RiskIntent = Field(default_factory=RiskIntent)
    # Things the request left genuinely open, and things the platform cannot do.
    # Populated by the extractor; a model may add to them.
    ambiguities: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)


class CompileError(ValueError):
    """The IR could not be turned into a valid StrategySpec."""


class _IndicatorAllocator:
    """Assigns stable, unique ids to the indicators a set of terms references.

    Two terms describing the same indicator with the same parameters share one id —
    which is both correct and what keeps a generated spec readable.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, IndicatorSpec] = {}
        self._counts: dict[str, int] = {}

    def resolve(self, term: Term) -> str:
        assert term.indicator is not None
        key = f"{term.indicator}|" + ",".join(
            f"{k}={term.params[k]:g}" for k in sorted(term.params)
        )
        existing = self._by_key.get(key)
        if existing is not None:
            return existing.id
        base = term.indicator.lower()
        # Fold the leading numeric parameter into the id so a spec reads as `ema_20`
        # rather than `ema_1`, which matters a great deal when a human reviews a
        # generated strategy. A counter suffix is added ONLY on a real collision,
        # so the common case (`ema_20` and `ema_50`) stays readable.
        numeric = next((f"{int(v)}" for _k, v in sorted(term.params.items()) if v), "")
        ident = f"{base}_{numeric}" if numeric else base
        if ident in {spec.id for spec in self._by_key.values()}:
            self._counts[ident] = self._counts.get(ident, 1) + 1
            ident = f"{ident}_{self._counts[ident]}"
        spec = IndicatorSpec(id=ident, type=term.indicator, params=dict(term.params))
        self._by_key[key] = spec
        return ident

    @property
    def specs(self) -> list[IndicatorSpec]:
        return list(self._by_key.values())


def _operand(term: Term, allocator: _IndicatorAllocator) -> Operand:
    if term.kind == "indicator":
        ref = allocator.resolve(term)
        output = term.output if term.output and term.output != "value" else None
        return Operand(kind="indicator", ref=ref, output=output, multiplier=term.multiplier)
    if term.kind == "price":
        return Operand(kind="price", field=term.field, multiplier=term.multiplier)
    return Operand(kind="const", value=term.value, multiplier=term.multiplier)


def _condition(rules: list[Rule], logic: str, allocator: _IndicatorAllocator) -> Condition:
    comparisons = [
        Comparison(
            left=_operand(rule.left, allocator),
            op=_OP_TO_DSL[rule.op],
            right=_operand(rule.right, allocator),
        )
        for rule in rules
    ]
    if len(comparisons) == 1:
        return comparisons[0]
    return Group(logic=logic, conditions=list(comparisons))


# Product defaults, applied when the request genuinely does not say. Every one of
# these is surfaced to the user as "we assumed X" rather than silently applied —
# an unstated stop is not the same as no stop, and the difference is the user's
# money in a paper account and their understanding of the result.
DEFAULT_TIMEFRAME: Timeframe = "1h"
DEFAULT_SYMBOL = "BTC/USD"
DEFAULT_STOP_PCT = 0.05
DEFAULT_SIZING_PCT = 0.10
DEFAULT_MAX_POSITION_PCT = 0.25


def compile_intent(intent: StrategyIntent) -> tuple[StrategySpec, list[str]]:
    """IR -> validated StrategySpec, plus the list of defaults that were applied.

    Raises :class:`CompileError` when the intent cannot produce a legal spec — the
    error text is fed back to the model for repair, so it is written to be actionable
    rather than merely accurate.
    """
    if not intent.entry:
        raise CompileError("no entry condition was specified; a strategy needs at least one")

    applied: list[str] = []
    allocator = _IndicatorAllocator()

    symbol = intent.symbol or DEFAULT_SYMBOL
    if intent.symbol is None:
        applied.append(f"instrument defaulted to {DEFAULT_SYMBOL}")
    timeframe = intent.timeframe or DEFAULT_TIMEFRAME
    if intent.timeframe is None:
        applied.append(f"timeframe defaulted to {DEFAULT_TIMEFRAME}")

    # Indicator allocation validates each IndicatorSpec against the catalog, so an
    # out-of-range parameter fails HERE. Converting it to a CompileError is what
    # turns it into an actionable repair message instead of an unhandled pydantic
    # error escaping to a 500.
    try:
        entry = _condition(intent.entry, intent.entry_logic, allocator)

        exit_rules: Condition | None = None
        if intent.exit.rules:
            exit_rules = _condition(intent.exit.rules, intent.exit.rules_logic, allocator)
    except CompileError:
        raise
    except Exception as exc:
        raise CompileError(f"an indicator or operand is invalid: {exc}") from exc

    stop = intent.exit.stop_loss_pct
    has_any_exit = any(
        v is not None
        for v in (
            stop,
            intent.exit.take_profit_pct,
            intent.exit.trailing_stop_pct,
            intent.exit.time_exit_bars,
            exit_rules,
        )
    )
    if not has_any_exit:
        # The DSL refuses a strategy with no way out, and rightly so. Rather than
        # failing the request, apply a conservative protective stop and SAY SO.
        stop = DEFAULT_STOP_PCT
        applied.append(f"no exit was specified; applied a {DEFAULT_STOP_PCT:.0%} protective stop")

    sizing_method = intent.sizing.method
    sizing_value = intent.sizing.value
    atr_ref: str | None = None
    if sizing_method == "atr":
        period = intent.sizing.atr_period or 14
        try:
            atr_ref = allocator.resolve(
                Term(kind="indicator", indicator="ATR", params={"period": float(period)})
            )
        except Exception as exc:
            raise CompileError(f"ATR sizing period is invalid: {exc}") from exc
    if sizing_method == "risk_per_trade" and stop is None:
        # risk-per-trade is defined by the distance to the stop; without one the DSL
        # rejects it. Falling back silently would change the risk profile entirely.
        sizing_method = "percent_equity"
        sizing_value = min(sizing_value, DEFAULT_SIZING_PCT)
        applied.append(
            "risk-per-trade sizing needs a stop loss; used percent-of-equity sizing instead"
        )

    try:
        spec = StrategySpec(
            name=intent.name or f"{symbol} strategy",
            universe=[symbol],
            timeframe=timeframe,
            indicators=allocator.specs,
            entry_long=entry,
            exit=ExitRule(
                stop_loss_pct=stop,
                take_profit_pct=intent.exit.take_profit_pct,
                trailing_stop_pct=intent.exit.trailing_stop_pct,
                time_exit_bars=intent.exit.time_exit_bars,
                exit_conditions=exit_rules,
            ),
            sizing=PositionSizing(method=sizing_method, value=sizing_value, atr_ref=atr_ref),
            risk=RiskLimits(
                max_position_pct=intent.risk.max_position_pct,
                max_open_positions=1,
                max_daily_loss_pct=intent.risk.max_daily_loss_pct,
                max_consecutive_losses=intent.risk.max_consecutive_losses,
            ),
        )
    except Exception as exc:
        raise CompileError(str(exc)) from exc
    return spec, applied
