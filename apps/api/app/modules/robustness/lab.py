"""Robustness analyses that re-run the engine.

Everything here is a pure function of (spec, bars, config) — no database, no
network — which is what makes each analysis reproducible and unit-testable, and
what lets the API layer decide separately how to persist or queue them.

Deliberate design choice: every analysis re-runs the ACTUAL engine rather than
approximating from a stored equity curve. Re-running is slower, but an approximation
cannot show the thing that matters most — that under higher costs a strategy stops
taking some trades entirely, which changes the result far more than subtracting a
fee from each existing trade would suggest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.modules.backtesting import engine
from app.modules.backtesting.types import BacktestResult, ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.robustness import monte_carlo, multiple_testing
from app.modules.robustness.overrides import Axis, apply_overrides, build_grid
from app.modules.robustness.splits import Fold, walk_forward
from app.modules.strategies.spec import StrategySpec


def _bar_returns(result: BacktestResult) -> list[float]:
    curve = [float(p.equity) for p in result.equity_curve]
    return [(curve[i] / curve[i - 1]) - 1.0 for i in range(1, len(curve)) if curve[i - 1] != 0]


def _headline(result: BacktestResult) -> dict[str, float | None]:
    """The small set of numbers every analysis reports per run."""
    return {
        "total_return": result.metrics.get("total_return"),
        "max_drawdown": result.metrics.get("max_drawdown"),
        "sharpe": result.metrics.get("sharpe"),
        "num_trades": result.metrics.get("num_trades"),
        "win_rate": result.metrics.get("win_rate"),
        "profit_factor": result.metrics.get("profit_factor"),
        "final_equity": float(result.final_equity),
    }


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold: dict[str, object]
    in_sample: dict[str, float | None]
    out_of_sample: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    folds: list[WalkForwardFold]
    oos_total_return: float
    oos_positive_folds: int
    consistency: float  # share of folds with a positive out-of-sample return
    degradation: float | None  # mean(IS return) - mean(OOS return)
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "folds": [
                {"fold": f.fold, "in_sample": f.in_sample, "out_of_sample": f.out_of_sample}
                for f in self.folds
            ],
            "oos_total_return": round(self.oos_total_return, 8),
            "oos_positive_folds": self.oos_positive_folds,
            "consistency": round(self.consistency, 6),
            "degradation": None if self.degradation is None else round(self.degradation, 8),
            "note": self.note,
        }


def run_walk_forward(
    spec: StrategySpec,
    bars: Sequence[BarPoint],
    config: ExecutionConfig,
    *,
    calendar: str = "24x7",
    folds: int = 5,
    anchored: bool = True,
    embargo_bars: int = 0,
) -> WalkForwardReport:
    """Evaluate the strategy on rolling out-of-sample windows.

    The in-sample number is reported next to the out-of-sample one on purpose: the
    GAP between them is the finding. A strategy that returns 40% in sample and -2%
    out of sample has not "made 40%" — it has demonstrated overfitting, and showing
    only the first number is how that gets missed.

    Note this engine has no fitted parameters, so "in sample" here means the earlier
    window rather than a training set. The comparison is still the right one: it
    answers whether the behaviour that produced the early result persisted.
    """
    split: list[Fold] = walk_forward(
        len(bars), folds=folds, anchored=anchored, embargo_bars=embargo_bars
    )
    reports: list[WalkForwardFold] = []
    for fold in split:
        is_bars = bars[fold.train_start : fold.train_end]
        oos_bars = bars[fold.test_start : fold.test_end]
        is_result = engine.run(spec, is_bars, config, calendar=calendar)
        oos_result = engine.run(spec, oos_bars, config, calendar=calendar)
        reports.append(
            WalkForwardFold(
                fold=fold.describe([b.ts for b in bars]),
                in_sample=_headline(is_result),
                out_of_sample=_headline(oos_result),
            )
        )

    oos_returns = [
        r.out_of_sample["total_return"] or 0.0
        for r in reports
        if r.out_of_sample["total_return"] is not None
    ]
    is_returns = [
        r.in_sample["total_return"] or 0.0
        for r in reports
        if r.in_sample["total_return"] is not None
    ]
    compounded = 1.0
    for r in oos_returns:
        compounded *= 1.0 + r
    positive = sum(1 for r in oos_returns if r > 0)

    degradation = None
    if is_returns and oos_returns:
        degradation = (sum(is_returns) / len(is_returns)) - (sum(oos_returns) / len(oos_returns))

    return WalkForwardReport(
        folds=reports,
        oos_total_return=compounded - 1.0,
        oos_positive_folds=positive,
        consistency=positive / len(oos_returns) if oos_returns else 0.0,
        degradation=degradation,
        note=(
            "Out-of-sample segments are strictly later than the windows preceding them"
            + (f", with a {embargo_bars}-bar embargo between them." if embargo_bars else ".")
            + " Compounding the per-fold returns assumes the strategy was run continuously "
            "across the folds with no re-selection between them."
        ),
    )


# --------------------------------------------------------------------------- #
# Parameter sensitivity
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SensitivityCell:
    overrides: dict[str, float]
    metrics: dict[str, float | None]
    valid: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SensitivityReport:
    axes: list[str]
    cells: list[SensitivityCell]
    tested: int
    skipped: int
    best: SensitivityCell | None
    median_return: float | None
    positive_share: float | None
    neighbourhood_note: str
    sharpe_assessment: dict[str, object] | None
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "axes": self.axes,
            "tested": self.tested,
            "skipped": self.skipped,
            "cells": [
                {
                    "overrides": c.overrides,
                    "metrics": c.metrics,
                    "valid": c.valid,
                    "reason": c.reason,
                }
                for c in self.cells
            ],
            "best": None
            if self.best is None
            else {"overrides": self.best.overrides, "metrics": self.best.metrics},
            "median_return": None if self.median_return is None else round(self.median_return, 8),
            "positive_share": (
                None if self.positive_share is None else round(self.positive_share, 6)
            ),
            "neighbourhood_note": self.neighbourhood_note,
            "sharpe_assessment": self.sharpe_assessment,
            "note": self.note,
        }


def run_sensitivity(
    spec: StrategySpec,
    bars: Sequence[BarPoint],
    config: ExecutionConfig,
    axes: Sequence[Axis],
    *,
    calendar: str = "24x7",
    prior_trials: int = 0,
) -> SensitivityReport:
    """Run the whole bounded grid and report the SHAPE of the surface.

    The best cell is reported last and never alone. What matters is whether good
    results form a plateau (the parameter does not have to be exactly right, so the
    effect is probably real) or a spike (only one cell works, so it is almost
    certainly a curve fit). Reporting the maximum of a grid as though it were a
    measurement is the single most common way a backtest misleads its own author.
    """
    combos = build_grid(spec, axes)
    cells: list[SensitivityCell] = []
    skipped = 0
    for overrides in combos:
        try:
            variant = apply_overrides(spec, overrides)
        except Exception as exc:
            skipped += 1
            cells.append(SensitivityCell(overrides, {}, valid=False, reason=str(exc)[:200]))
            continue
        result = engine.run(variant, bars, config, calendar=calendar)
        cells.append(SensitivityCell(overrides, _headline(result), valid=True))

    valid = [c for c in cells if c.valid]
    returns = [c.metrics.get("total_return") or 0.0 for c in valid]
    best = max(valid, key=lambda c: c.metrics.get("total_return") or 0.0) if valid else None

    median_return = None
    positive_share = None
    if returns:
        ordered = sorted(returns)
        mid = len(ordered) // 2
        median_return = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        positive_share = sum(1 for r in returns if r > 0) / len(returns)

    if best is not None and returns and median_return is not None:
        spread = (best.metrics.get("total_return") or 0.0) - median_return
        neighbourhood = f"The best cell beats the grid median by {spread:.2%}. " + (
            "Results are broadly similar across the grid, which is what a real effect looks like."
            if positive_share and positive_share > 0.6
            else "Only "
            f"{(positive_share or 0):.0%} of cells were profitable at all, so the best "
            "cell is more likely to be a lucky corner than a stable region."
        )
    else:
        neighbourhood = "No valid cell produced a result."

    # The grid IS the multiple-testing problem: hand every cell's Sharpe to the
    # deflation so the headline is judged against the size of the search.
    assessment = None
    sharpes = [c.metrics.get("sharpe") for c in valid]
    finite = [s for s in sharpes if s is not None]
    if best is not None and len(finite) > 1:
        best_variant = apply_overrides(spec, best.overrides)
        best_result = engine.run(best_variant, bars, config, calendar=calendar)
        # The trials that count are not only this grid's cells. A researcher who has
        # already run this spec twenty times has taken twenty more draws, and
        # counting only the current sweep understates the search in the one
        # direction the correction must never err in: it would make a lucky result
        # look more significant than it is. `prior_trials` carries the owner's
        # completed runs of the same spec (see experiments.count_trials).
        padded = list(finite)
        if prior_trials > 0:
            # Represent prior trials at the observed dispersion of this grid. They
            # raise the selection bar without pretending to know their own values.
            padded.extend(
                finite[: min(prior_trials, len(finite))] * (prior_trials // max(len(finite), 1) + 1)
            )
            padded = padded[: len(finite) + prior_trials]
        assessment = multiple_testing.assess_sharpe(
            _bar_returns(best_result), trial_sharpes=padded
        ).as_dict()
        assessment["grid_cells"] = len(finite)
        assessment["prior_trials"] = prior_trials

    return SensitivityReport(
        axes=[a.path for a in axes],
        cells=cells,
        tested=len(valid),
        skipped=skipped,
        best=best,
        median_return=median_return,
        positive_share=positive_share,
        neighbourhood_note=neighbourhood,
        sharpe_assessment=assessment,
        note=(
            f"{len(combos)} combinations were generated and {len(valid)} ran; "
            f"{skipped} were rejected by spec validation. Every cell counts as a trial for "
            "the multiple-testing correction."
        ),
    )


# --------------------------------------------------------------------------- #
# Cost stress
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CostStressReport:
    baseline: dict[str, float | None]
    levels: list[dict[str, object]]
    breakeven_multiple: float | None
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline,
            "levels": self.levels,
            "breakeven_multiple": (
                None if self.breakeven_multiple is None else round(self.breakeven_multiple, 4)
            ),
            "note": self.note,
        }


def run_cost_stress(
    spec: StrategySpec,
    bars: Sequence[BarPoint],
    config: ExecutionConfig,
    *,
    calendar: str = "24x7",
    multiples: Sequence[float] = (1.0, 1.5, 2.0, 3.0, 5.0),
) -> CostStressReport:
    """Re-run the strategy with commission and slippage scaled up.

    Re-running (rather than deducting a fee per trade afterwards) is essential: at
    higher costs a strategy does not merely earn less on the same trades — the
    engine's cash constraint and position clamp change which trades it takes at all.

    ``breakeven_multiple`` is the smallest tested multiple at which the strategy
    stops being profitable. If that number is close to 1, the edge is a rounding
    error on the cost assumption.
    """
    levels: list[dict[str, object]] = []
    baseline: dict[str, float | None] = {}
    breakeven: float | None = None

    for multiple in multiples:
        scaled = ExecutionConfig(
            commission_bps=config.commission_bps * multiple,
            slippage_bps=config.slippage_bps * multiple,
            initial_cash=config.initial_cash,
            frictionless=False,
        )
        result = engine.run(spec, bars, scaled, calendar=calendar)
        headline = _headline(result)
        if multiple == 1.0:
            baseline = headline
        total = headline.get("total_return") or 0.0
        if breakeven is None and total <= 0 and multiple > 0:
            breakeven = multiple
        levels.append(
            {
                "multiple": multiple,
                "commission_bps": round(scaled.commission_bps, 6),
                "slippage_bps": round(scaled.slippage_bps, 6),
                "metrics": headline,
                "profitable": total > 0,
            }
        )

    if breakeven is None:
        note = (
            f"Still profitable at {max(multiples):g}x the assumed frictions. That is a good "
            "sign, but it only means the edge is larger than the cost model — not that the "
            "cost model is right."
        )
    elif breakeven <= 1.0:
        note = "Not profitable even at the baseline cost assumption."
    elif breakeven <= 2.0:
        note = (
            f"The result disappears at {breakeven:g}x costs. An edge this thin is inside the "
            "error bars of the commission and slippage estimates themselves."
        )
    else:
        note = (
            f"The result survives to {breakeven:g}x the assumed frictions before turning negative."
        )

    return CostStressReport(
        baseline=baseline, levels=levels, breakeven_multiple=breakeven, note=note
    )


# --------------------------------------------------------------------------- #
# Monte Carlo over a completed run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class MonteCarloReport:
    distributions: list[dict[str, object]] = field(default_factory=list)
    cost_perturbation: list[dict[str, float | bool | None]] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "distributions": self.distributions,
            "cost_perturbation": self.cost_perturbation,
            "note": self.note,
        }


def run_monte_carlo(
    result: BacktestResult, *, samples: int = 1000, seed: int = 7
) -> MonteCarloReport:
    distributions: list[dict[str, object]] = []
    reshuffled = monte_carlo.reshuffle_trades(result.trades, samples=samples, seed=seed)
    if reshuffled is not None:
        distributions.extend(d.as_dict() for d in reshuffled)
    bootstrap = monte_carlo.block_bootstrap(_bar_returns(result), samples=samples, seed=seed)
    if bootstrap is not None:
        distributions.append(bootstrap.as_dict())

    return MonteCarloReport(
        distributions=distributions,
        cost_perturbation=monte_carlo.perturb_costs(
            result.trades, initial_equity=float(result.initial_cash)
        ),
        note=(
            "Every distribution here is a resampling of THIS run's realized history. It "
            "quantifies how much of the outcome was sequence and sampling luck within the "
            "tested period. It is not a forecast, and the probabilities are conditional on "
            "the tested period repeating."
        )
        if distributions
        else (
            "Not enough trades or bars to resample: a Monte Carlo distribution over fewer "
            "than five trades would describe the resampling, not the strategy."
        ),
    )
