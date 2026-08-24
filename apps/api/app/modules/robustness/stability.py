"""The stability assessment.

This is deliberately NOT an AI-generated score, and deliberately not a single
number with a mysterious provenance. It is a checklist: a fixed set of named
checks, each with its own threshold, each reporting the evidence that produced its
verdict. A reader who disagrees with a threshold can see exactly which check it
belongs to and discount it.

Design rules:

* Every check is derived from a deterministic analysis, never from a language model.
* A check that lacks the data to run reports ``insufficient_evidence`` — it never
  quietly passes. "We could not test this" and "this passed" must not look alike.
* The headline verdict is the WEAKEST link, not an average. Averaging lets four
  cosmetic passes bury one fatal failure, which is precisely the error the whole
  module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.robustness.lab import (
    CostStressReport,
    MonteCarloReport,
    SensitivityReport,
    WalkForwardReport,
)

Verdict = Literal["pass", "warn", "fail", "insufficient_evidence"]

_ORDER: dict[Verdict, int] = {
    "pass": 0,
    "insufficient_evidence": 1,
    "warn": 2,
    "fail": 3,
}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    verdict: Verdict
    detail: str
    evidence: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class StabilityAssessment:
    verdict: Verdict
    checks: list[Check]
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "checks": [c.as_dict() for c in self.checks],
            "method": (
                "Each check is a deterministic threshold on a specific analysis. The overall "
                "verdict is the worst individual verdict, not an average, so a single fatal "
                "result cannot be diluted by cosmetic passes. No language model is involved "
                "in producing this assessment."
            ),
        }


# --- thresholds, named and in one place so they can be argued with -----------
MIN_TRADES = 20
MIN_OOS_CONSISTENCY = 0.5
MIN_COST_BREAKEVEN_MULTIPLE = 2.0
MIN_GRID_POSITIVE_SHARE = 0.5
MIN_DEFLATED_SHARPE = 0.90
MAX_ACCEPTABLE_DRAWDOWN = -0.35


def _check_sample(metrics: dict[str, float | None]) -> Check:
    trades = int(metrics.get("num_trades") or 0)
    if trades == 0:
        return Check(
            "sample_size",
            "insufficient_evidence",
            "The strategy took no trades, so there is nothing to evaluate.",
            {"num_trades": 0},
        )
    if trades < MIN_TRADES:
        return Check(
            "sample_size",
            "warn",
            f"{trades} trades is below the {MIN_TRADES} needed for any statistic here to "
            "carry weight. Every result below should be read as provisional.",
            {"num_trades": trades, "minimum": MIN_TRADES},
        )
    return Check(
        "sample_size",
        "pass",
        f"{trades} trades is enough for the statistics below to be meaningful.",
        {"num_trades": trades, "minimum": MIN_TRADES},
    )


def _check_out_of_sample(report: WalkForwardReport | None) -> Check:
    if report is None or not report.folds:
        return Check(
            "out_of_sample",
            "insufficient_evidence",
            "No walk-forward analysis was run, so nothing here is out of sample.",
            {},
        )
    evidence: dict[str, object] = {
        "consistency": report.consistency,
        "oos_total_return": report.oos_total_return,
        "degradation": report.degradation,
        "folds": len(report.folds),
    }
    if report.oos_total_return <= 0:
        return Check(
            "out_of_sample",
            "fail",
            f"Compounded out-of-sample return is {report.oos_total_return:.2%}. Whatever the "
            "in-sample figure shows, the strategy did not work on data that came after it.",
            evidence,
        )
    if report.consistency < MIN_OOS_CONSISTENCY:
        return Check(
            "out_of_sample",
            "warn",
            f"Only {report.consistency:.0%} of out-of-sample folds were profitable. A positive "
            "total driven by a minority of windows usually means one lucky period, not an edge.",
            evidence,
        )
    return Check(
        "out_of_sample",
        "pass",
        f"{report.consistency:.0%} of out-of-sample folds were profitable, compounding to "
        f"{report.oos_total_return:.2%}.",
        evidence,
    )


def _check_costs(report: CostStressReport | None) -> Check:
    if report is None or not report.levels:
        return Check("cost_sensitivity", "insufficient_evidence", "No cost stress was run.", {})
    evidence: dict[str, object] = {"breakeven_multiple": report.breakeven_multiple}
    if report.breakeven_multiple is None:
        return Check(
            "cost_sensitivity",
            "pass",
            "The result survives every cost multiple tested. That bounds the risk from the "
            "cost assumption; it does not validate the assumption itself.",
            evidence,
        )
    multiple = report.breakeven_multiple
    if multiple <= 1.0:
        return Check(
            "cost_sensitivity", "fail", "Not profitable at the baseline cost assumption.", evidence
        )
    if multiple < MIN_COST_BREAKEVEN_MULTIPLE:
        return Check(
            "cost_sensitivity",
            "fail",
            f"The edge disappears at {multiple:g}x costs, inside the error bars of the "
            "commission and slippage estimates themselves, so it is not distinguishable from a "
            "cost-model artefact.",
            evidence,
        )
    return Check(
        "cost_sensitivity", "pass", f"Survives to {multiple:g}x the assumed frictions.", evidence
    )


def _check_parameters(report: SensitivityReport | None) -> Check:
    if report is None or not report.tested:
        return Check(
            "parameter_stability", "insufficient_evidence", "No parameter sweep was run.", {}
        )
    evidence: dict[str, object] = {
        "positive_share": report.positive_share,
        "tested": report.tested,
        "median_return": report.median_return,
    }
    if report.positive_share is None:
        return Check(
            "parameter_stability",
            "insufficient_evidence",
            "The sweep produced no valid cells.",
            evidence,
        )
    share = report.positive_share
    if share < MIN_GRID_POSITIVE_SHARE:
        return Check(
            "parameter_stability",
            "warn",
            f"Only {share:.0%} of the parameter grid was profitable. The chosen values sit on a "
            "narrow spike rather than a plateau, which is the signature of a curve fit.",
            evidence,
        )
    return Check(
        "parameter_stability",
        "pass",
        f"{share:.0%} of the parameter grid was profitable, so the result does not depend on "
        "hitting one exact combination.",
        evidence,
    )


def _check_multiple_testing(report: SensitivityReport | None) -> Check:
    assessment = report.sharpe_assessment if report is not None else None
    if not assessment:
        return Check(
            "multiple_testing",
            "insufficient_evidence",
            "No search was recorded, so no selection correction could be applied. A single "
            "untuned run needs none; a tuned one does.",
            {},
        )
    dsr = assessment.get("deflated_sharpe")
    verdict_text = str(assessment.get("verdict", ""))
    evidence: dict[str, object] = {
        "deflated_sharpe": dsr,
        "trials": assessment.get("trials"),
        "expected_max_sharpe": assessment.get("expected_max_sharpe"),
    }
    if not isinstance(dsr, int | float):
        return Check("multiple_testing", "insufficient_evidence", verdict_text, evidence)
    if dsr < 0.5:
        return Check("multiple_testing", "fail", verdict_text, evidence)
    if dsr < MIN_DEFLATED_SHARPE:
        return Check("multiple_testing", "warn", verdict_text, evidence)
    return Check("multiple_testing", "pass", verdict_text, evidence)


def _check_drawdown(metrics: dict[str, float | None]) -> Check:
    dd = metrics.get("max_drawdown")
    if dd is None:
        return Check("drawdown", "insufficient_evidence", "No drawdown was computed.", {})
    evidence: dict[str, object] = {"max_drawdown": dd, "threshold": MAX_ACCEPTABLE_DRAWDOWN}
    if dd < MAX_ACCEPTABLE_DRAWDOWN:
        return Check(
            "drawdown",
            "warn",
            f"Peak-to-trough drawdown reached {dd:.1%}. Whatever the return, a decline of this "
            "size is the thing that ends a strategy in practice.",
            evidence,
        )
    return Check("drawdown", "pass", f"Maximum drawdown {dd:.1%}.", evidence)


def _check_sequence_risk(report: MonteCarloReport | None) -> Check:
    if report is None or not report.distributions:
        return Check("sequence_risk", "insufficient_evidence", "No resampling was run.", {})
    match = next(
        (d for d in report.distributions if d.get("method") == "trade_reshuffle_drawdown"), None
    )
    if match is None:
        return Check(
            "sequence_risk", "insufficient_evidence", "No drawdown distribution was produced.", {}
        )
    raw_observed, raw_p05 = match.get("observed"), match.get("p05")
    observed = float(raw_observed) if isinstance(raw_observed, int | float) else 0.0
    p05 = float(raw_p05) if isinstance(raw_p05, int | float) else 0.0
    evidence: dict[str, object] = {"observed_drawdown": observed, "p05_drawdown": p05}
    if p05 < observed * 1.5 and p05 < -0.2:
        return Check(
            "sequence_risk",
            "warn",
            f"Reordering the same trades produces a 5th-percentile drawdown of {p05:.1%} against "
            f"the {observed:.1%} that actually occurred. The realized path was materially "
            "luckier than the average ordering of its own trades.",
            evidence,
        )
    return Check(
        "sequence_risk",
        "pass",
        f"Reshuffling the trade order does not produce a materially worse drawdown "
        f"(5th percentile {p05:.1%} vs {observed:.1%} realized).",
        evidence,
    )


def assess(
    *,
    metrics: dict[str, float | None],
    walk_forward: WalkForwardReport | None = None,
    sensitivity: SensitivityReport | None = None,
    cost_stress: CostStressReport | None = None,
    monte_carlo: MonteCarloReport | None = None,
) -> StabilityAssessment:
    """Run every check and take the WEAKEST verdict as the headline."""
    checks = [
        _check_sample(metrics),
        _check_out_of_sample(walk_forward),
        _check_costs(cost_stress),
        _check_parameters(sensitivity),
        _check_multiple_testing(sensitivity),
        _check_drawdown(metrics),
        _check_sequence_risk(monte_carlo),
    ]
    worst = max(checks, key=lambda c: _ORDER[c.verdict])
    failures = [c.name for c in checks if c.verdict == "fail"]
    warnings = [c.name for c in checks if c.verdict == "warn"]
    missing = [c.name for c in checks if c.verdict == "insufficient_evidence"]

    if failures:
        summary = (
            f"Failed on {', '.join(failures)}. A strategy that fails any one of these has not "
            "demonstrated an edge, regardless of how good its headline backtest looks."
        )
    elif warnings:
        summary = (
            f"Passed the hard checks but raised concerns on {', '.join(warnings)}. Treat the "
            "result as a hypothesis worth more data, not as a validated strategy."
        )
    elif missing:
        summary = (
            f"No check failed, but {', '.join(missing)} could not be evaluated. Absence of "
            "evidence is not a pass; run the missing analyses before drawing a conclusion."
        )
    else:
        summary = (
            "Passed every robustness check that was run. That means the result survived "
            "out-of-sample evaluation, cost stress, a parameter sweep, and a selection "
            "correction, not that it will work in future markets."
        )
    return StabilityAssessment(verdict=worst.verdict, checks=checks, summary=summary)
