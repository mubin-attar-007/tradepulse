"""Evaluation case definitions.

An evaluation case states what a request must produce, in terms a machine can check
without a second language model in the loop. That constraint shapes the whole
design: expectations are expressed against the IR's own vocabulary (indicators,
periods, operators, stops), which is exactly what the semantic checker already
compares, so a case is verifiable rather than merely plausible.

Categories, and what each is really testing:

* ``valid``       — can the pipeline turn a clear request into the RIGHT strategy?
                    Not a valid strategy: the right one.
* ``ambiguous``   — does it ask rather than guess? Both directions matter, so cases
                    also assert that a clear request raises NO clarification.
* ``unsupported`` — does it refuse, with a reason, instead of substituting something
                    nearby that the user did not ask for?
* ``safety``      — does a request for real-money execution, guaranteed returns or
                    insider information get refused rather than served?
* ``injection``   — is request text treated as data when it contains instructions?
* ``grounding``   — does narration cite only numbers it was given?
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Category = Literal["valid", "ambiguous", "unsupported", "safety", "injection", "grounding"]

DATASET_VERSION = "1.0.0"
DATASET_DIR = Path(__file__).parent / "datasets"


@dataclass(frozen=True, slots=True)
class Expectation:
    """What a correct answer looks like. Every field is optional and only checked
    when present, so a case asserts exactly what it means to assert."""

    status: Literal["ok", "refused", "failed"] | None = None
    symbol: str | None = None
    timeframe: str | None = None
    # Indicator TYPES that must appear, e.g. ["EMA"]. A strategy that answers an EMA
    # request with an SMA is the canonical silent failure.
    indicators: tuple[str, ...] = ()
    # "EMA:20" style, so a swapped period is caught.
    periods: tuple[str, ...] = ()
    entry_ops: tuple[str, ...] = ()
    exit_ops: tuple[str, ...] = ()
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    sizing_method: str | None = None
    # Substrings that must appear among the reported ambiguities / refusals.
    ambiguity_contains: tuple[str, ...] = ()
    unsupported_contains: tuple[str, ...] = ()
    # Assert the ABSENCE of clarification, so over-asking is penalised too.
    expect_no_ambiguity: bool = False

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> Expectation:
        return Expectation(
            status=payload.get("status"),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
            indicators=tuple(payload.get("indicators", ())),
            periods=tuple(payload.get("periods", ())),
            entry_ops=tuple(payload.get("entry_ops", ())),
            exit_ops=tuple(payload.get("exit_ops", ())),
            stop_loss_pct=payload.get("stop_loss_pct"),
            take_profit_pct=payload.get("take_profit_pct"),
            trailing_stop_pct=payload.get("trailing_stop_pct"),
            sizing_method=payload.get("sizing_method"),
            ambiguity_contains=tuple(payload.get("ambiguity_contains", ())),
            unsupported_contains=tuple(payload.get("unsupported_contains", ())),
            expect_no_ambiguity=bool(payload.get("expect_no_ambiguity", False)),
        )


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    category: Category
    request: str
    expect: Expectation
    notes: str = ""
    # Free-form labels for slicing results ("crossover", "rsi", "risk-only").
    tags: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> EvalCase:
        return EvalCase(
            id=payload["id"],
            category=payload["category"],
            request=payload["request"],
            expect=Expectation.from_dict(payload.get("expect", {})),
            notes=payload.get("notes", ""),
            tags=tuple(payload.get("tags", ())),
        )


def load_cases(
    *, categories: set[str] | None = None, directory: Path | None = None
) -> list[EvalCase]:
    """Every case on disk, optionally filtered by category.

    Datasets are plain JSON so a case can be reviewed in a pull request by someone
    who does not read Python — which is the point of having a dataset rather than a
    pile of assertions.
    """
    directory = directory or DATASET_DIR
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload["cases"]:
            case = EvalCase.from_dict(raw)
            if case.id in seen:
                raise ValueError(f"duplicate evaluation case id {case.id!r} in {path.name}")
            seen.add(case.id)
            if categories and case.category not in categories:
                continue
            cases.append(case)
    return cases
