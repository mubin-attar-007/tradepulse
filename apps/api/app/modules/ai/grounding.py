"""Deterministic grounding checks for generated narration.

The claim "the AI only uses numbers present in the data" was previously enforced by
asking it nicely in the system prompt. That is not enforcement, it is hope, and it
is unfalsifiable from the outside — which is exactly the shape of claim this project
is not allowed to make.

So narration is checked ARITHMETICALLY. Every number in the generated text is
extracted and matched against the evidence payload the model was given, in every
form the evidence could reasonably be written in (a raw value, a percentage, a
rounded version). A number that matches nothing is an unsupported claim, and it is
reported as one.

Deliberately NOT an LLM judge. A judge would be another unverifiable opinion in the
loop; this produces a list a human can check by hand in thirty seconds. An LLM judge
is a reasonable ADDITION later for things arithmetic cannot see (tone, causal
claims), but never as the primary check.

Known and accepted limits, stated because a check whose blind spots are hidden is
worse than no check: small integers ("3 trades") can coincide with an unrelated
value in the evidence, and the checker does not verify that a number is used in the
right CONTEXT — only that the model did not invent it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Numbers written the way people write them, including percentages and negatives.
# The comma-grouped branch REQUIRES a comma group (`+`, not `*`): with `*` it matched
# the leading "100" of "100494.89" and left "494.89" behind as a separate token, so a
# perfectly grounded figure was reported as invented.
_NUMBER = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|-?\d+(?:\.\d+)?%?")

# Numbers that carry no claim: years, small counts in ordinary prose, and the
# ubiquitous 0/1/2/100. Flagging these produces noise that trains readers to ignore
# the checker, which costs more than the rare miss.
_UNREMARKABLE = {0.0, 1.0, 2.0, 3.0, 100.0}

# Phrases that assert a cause the data cannot establish. A simulation shows what
# happened, never why.
_CAUSAL = re.compile(
    r"\b(?:because|due to|driven by|caused by|thanks to|as a result of|owing to)\b", re.I
)

# Language that turns a historical simulation into a forward-looking promise.
_PREDICTIVE = re.compile(
    r"\b(?:will (?:make|earn|return|profit|continue)|should (?:make|earn|return|profit)|"
    r"expect(?:ed)? to (?:make|earn|return)|guarantee\w*|risk[- ]free|"
    r"consistently profitable|proven strategy)\b",
    re.I,
)


@dataclass
class GroundingReport:
    supported_numbers: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    causal_claims: list[str] = field(default_factory=list)
    predictive_claims: list[str] = field(default_factory=list)
    has_disclosure: bool = False

    @property
    def ok(self) -> bool:
        return not self.unsupported_numbers and not self.predictive_claims and self.has_disclosure

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "supported_numbers": self.supported_numbers,
            "unsupported_numbers": self.unsupported_numbers,
            "causal_claims": self.causal_claims,
            "predictive_claims": self.predictive_claims,
            "has_disclosure": self.has_disclosure,
            "method": (
                "Every number in the text is matched against the evidence the model was "
                "given, in raw, percentage and rounded forms. No language model is used "
                "to judge this."
            ),
        }


def _candidate_values(evidence: Any) -> set[float]:
    """Every numeric value the model was allowed to cite, in every plausible form.

    A metric of 0.0374 may legitimately be written as 0.0374, 3.74%, 3.7% or 4%, so
    each of those is a valid rendering of the same fact and must not be flagged.
    """
    values: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list | tuple):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, int | float):
            add(float(node))
        elif isinstance(node, str):
            # Money crosses the API as a decimal string, so it arrives here as text.
            try:
                add(float(node))
            except ValueError:
                return

    def add(value: float) -> None:
        values.add(value)
        values.add(abs(value))
        for places in (0, 1, 2, 3, 4):
            values.add(round(value, places))
            values.add(round(abs(value), places))
            values.add(round(value * 100, places))
            values.add(round(abs(value) * 100, places))

    walk(evidence)
    return values


def check_grounding(text: str, evidence: Any) -> GroundingReport:
    """Match every number in ``text`` against ``evidence``."""
    allowed = _candidate_values(evidence)
    report = GroundingReport()

    for raw in _NUMBER.findall(text):
        token = raw.rstrip("%").replace(",", "")
        try:
            value = float(token)
        except ValueError:
            continue
        if value in _UNREMARKABLE:
            continue
        candidates = {value, abs(value)}
        for places in (0, 1, 2, 3, 4):
            candidates.add(round(value, places))
            candidates.add(round(abs(value), places))
        if candidates & allowed:
            report.supported_numbers.append(raw)
        else:
            report.unsupported_numbers.append(raw)

    for match in _CAUSAL.finditer(text):
        start = max(0, match.start() - 60)
        report.causal_claims.append(text[start : match.end() + 60].strip())
    for match in _PREDICTIVE.finditer(text):
        start = max(0, match.start() - 40)
        report.predictive_claims.append(text[start : match.end() + 40].strip())

    lowered = text.lower()
    report.has_disclosure = (
        "not investment advice" in lowered
        or "historical simulation" in lowered
        or "not financial advice" in lowered
    )
    return report
