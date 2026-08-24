"""A closed, bounded language for varying a StrategySpec.

A parameter sweep needs to change a spec programmatically. The obvious
implementation — accept a dotted path and `setattr` down it — quietly becomes an
arbitrary-mutation primitive, and this is a system where an LLM proposes the
inputs. So the addressable surface is a CLOSED WHITELIST of numeric leaves, exactly
mirroring the DSL's own philosophy:

    exit.stop_loss_pct
    exit.take_profit_pct
    exit.trailing_stop_pct
    exit.time_exit_bars
    sizing.value
    risk.max_position_pct
    risk.max_daily_loss_pct
    risk.max_consecutive_losses
    indicators.<indicator id>.params.<param name>

Anything else is rejected. Every override is applied to the spec's JSON form and
then RE-VALIDATED through StrategySpec, so a swept value cannot bypass a single
range check, capability guard, or cross-field rule that a hand-authored spec has to
satisfy.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.strategies.spec import StrategySpec

_SIMPLE_PATHS = {
    "exit.stop_loss_pct",
    "exit.take_profit_pct",
    "exit.trailing_stop_pct",
    "exit.time_exit_bars",
    "sizing.value",
    "risk.max_position_pct",
    "risk.max_daily_loss_pct",
    "risk.max_consecutive_losses",
}
_INTEGER_PATHS = {"exit.time_exit_bars", "risk.max_consecutive_losses"}
_INDICATOR_PATH = re.compile(r"^indicators\.([a-zA-Z][a-zA-Z0-9_]*)\.params\.([a-zA-Z_]+)$")

# A sweep is a search, and an unbounded search is both a compute DoS and a
# multiple-testing disaster. Both limits are reported alongside any result.
MAX_AXES = 3
MAX_VALUES_PER_AXIS = 25
MAX_COMBINATIONS = 200


class OverrideError(ValueError):
    """An override that is not addressable, or a grid that is too large."""


@dataclass(frozen=True, slots=True)
class Axis:
    """One swept parameter and the values to try."""

    path: str
    values: tuple[float, ...]

    def label(self, value: float) -> str:
        return f"{self.path}={value:g}"


def validate_path(path: str, spec: StrategySpec) -> None:
    """Reject anything outside the whitelist, and any indicator/param that does not exist."""
    if path in _SIMPLE_PATHS:
        return
    match = _INDICATOR_PATH.match(path)
    if not match:
        raise OverrideError(
            f"'{path}' is not a sweepable parameter. Allowed: {sorted(_SIMPLE_PATHS)} "
            "or indicators.<id>.params.<name>."
        )
    indicator_id, param = match.groups()
    indicator = next((i for i in spec.indicators if i.id == indicator_id), None)
    if indicator is None:
        raise OverrideError(f"unknown indicator '{indicator_id}' in '{path}'")
    if param not in indicator.params:
        raise OverrideError(
            f"indicator '{indicator_id}' ({indicator.type}) has no parameter '{param}'"
        )


def apply_overrides(spec: StrategySpec, overrides: dict[str, float]) -> StrategySpec:
    """Return a NEW spec with ``overrides`` applied, re-validated from scratch.

    Re-validation is the whole safety story: a swept value goes through exactly the
    same Pydantic model as a hand-authored one, so an out-of-range period or a
    risk_per_trade left without a stop fails here rather than producing a run with
    quietly different semantics.
    """
    for path in overrides:
        validate_path(path, spec)
    data: dict[str, Any] = spec.model_dump(mode="json")

    for path, raw in overrides.items():
        value: float | int = int(raw) if path in _INTEGER_PATHS else raw
        if path in _SIMPLE_PATHS:
            section, field = path.split(".", 1)
            data[section][field] = value
            continue
        match = _INDICATOR_PATH.match(path)
        assert match is not None  # validate_path already guaranteed this
        indicator_id, param = match.groups()
        for indicator in data["indicators"]:
            if indicator["id"] == indicator_id:
                indicator["params"][param] = value
                break

    try:
        return StrategySpec.model_validate(data)
    except Exception as exc:  # pragma: no cover - message shape only
        raise OverrideError(f"overrides produced an invalid strategy: {exc}") from exc


def build_grid(spec: StrategySpec, axes: Sequence[Axis]) -> list[dict[str, float]]:
    """Every combination of the axes, bounded and validated.

    Combinations that fail spec validation (for example a fast period that would
    exceed a slow one) are DROPPED rather than raising, because a rectangular grid
    over a constrained space always contains some invalid corners — but the count of
    dropped cells is reported by the caller so the sweep's real size is never
    overstated.
    """
    if len(axes) > MAX_AXES:
        raise OverrideError(f"at most {MAX_AXES} axes may be swept at once (got {len(axes)})")
    for axis in axes:
        validate_path(axis.path, spec)
        if not axis.values:
            raise OverrideError(f"axis '{axis.path}' has no values")
        if len(axis.values) > MAX_VALUES_PER_AXIS:
            raise OverrideError(
                f"axis '{axis.path}' has {len(axis.values)} values; the maximum is "
                f"{MAX_VALUES_PER_AXIS}"
            )
    total = 1
    for axis in axes:
        total *= len(axis.values)
    if total > MAX_COMBINATIONS:
        raise OverrideError(
            f"grid of {total} combinations exceeds the {MAX_COMBINATIONS} cap. A larger search "
            "also needs a larger multiple-testing correction, which usually means the result "
            "would not survive it."
        )

    combos: list[dict[str, float]] = []
    for values in itertools.product(*[axis.values for axis in axes]):
        combos.append({axis.path: value for axis, value in zip(axes, values, strict=True)})
    return combos
