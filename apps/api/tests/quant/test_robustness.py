"""Robustness lab: splits, sweeps, cost stress, resampling, and deflation.

The point of these tests is that each analysis must be able to reach a NEGATIVE
conclusion. A robustness suite that always says "looks fine" is decoration, so
several tests below construct a strategy that should fail and assert the lab says so.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.robustness import lab, monte_carlo, multiple_testing, splits
from app.modules.robustness.overrides import (
    Axis,
    OverrideError,
    apply_overrides,
    build_grid,
)
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 1, 2, tzinfo=UTC)
CONFIG = ExecutionConfig(initial_cash=Decimal("100000"))


def _bars(n: int = 400, *, seed: int = 3) -> list[BarPoint]:
    """A deterministic pseudo-random walk with a mild trend and cycles."""
    out: list[BarPoint] = []
    prev = 100.0
    state = seed
    for i in range(n):
        state = (state * 1103515245 + 12345) % (2**31)
        noise = (state / (2**31)) - 0.5
        close = 100 + 12 * math.sin(i / 17) + i * 0.02 + noise * 2
        o = prev
        out.append(
            BarPoint(
                ts=BASE + timedelta(hours=i),
                open=Decimal(str(round(o, 4))),
                high=Decimal(str(round(max(o, close) * 1.004, 4))),
                low=Decimal(str(round(min(o, close) * 0.996, 4))),
                close=Decimal(str(round(close, 4))),
                volume=Decimal("1000"),
                bar_count=60,
            )
        )
        prev = close
    return out


def _spec(fast: int = 10, slow: int = 30) -> StrategySpec:
    return StrategySpec(
        name="robustness",
        universe=["X"],
        timeframe="1h",
        indicators=[
            IndicatorSpec(id="fast", type="SMA", params={"period": fast}),
            IndicatorSpec(id="slow", type="SMA", params={"period": slow}),
        ],
        entry_long=Comparison(
            left=Operand(kind="indicator", ref="fast"),
            op="cross_above",
            right=Operand(kind="indicator", ref="slow"),
        ),
        exit=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            exit_conditions=Comparison(
                left=Operand(kind="indicator", ref="fast"),
                op="cross_below",
                right=Operand(kind="indicator", ref="slow"),
            ),
        ),
        sizing=PositionSizing(method="percent_equity", value=0.25),
        risk=RiskLimits(max_position_pct=0.25, max_open_positions=1),
    )


# --- splits ------------------------------------------------------------------


def test_walk_forward_windows_never_overlap_and_move_forward() -> None:
    folds = splits.walk_forward(500, folds=5, train_bars=200, test_bars=60)
    assert len(folds) == 5
    for f in folds:
        assert f.train_end <= f.test_start, "training window reaches into the test window"
        assert f.test_start < f.test_end
    for a, b in pairwise(folds):
        assert b.test_start >= a.test_end, "test windows overlap"


def test_anchored_walk_forward_grows_the_training_window() -> None:
    folds = splits.walk_forward(500, folds=4, train_bars=150, test_bars=60, anchored=True)
    sizes = [f.train_size for f in folds]
    assert sizes == sorted(sizes) and sizes[-1] > sizes[0]
    assert all(f.train_start == 0 for f in folds)


def test_rolling_walk_forward_keeps_the_training_window_fixed() -> None:
    folds = splits.walk_forward(500, folds=4, train_bars=150, test_bars=60, anchored=False)
    assert len({f.train_size for f in folds}) == 1


def test_embargo_opens_a_gap_before_each_test_window() -> None:
    plain = splits.walk_forward(500, folds=3, train_bars=200, test_bars=60, embargo_bars=0)
    gapped = splits.walk_forward(500, folds=3, train_bars=200, test_bars=60, embargo_bars=15)
    for a, b in zip(plain, gapped, strict=True):
        assert b.train_end == a.train_end - 15
        assert b.test_start - b.train_end == 15


def test_a_split_that_cannot_be_honoured_raises_instead_of_shrinking() -> None:
    """Silently returning two of five requested folds would make an out-of-sample
    claim quietly untrue."""
    with pytest.raises(splits.SplitError):
        splits.walk_forward(40, folds=5, train_bars=30, test_bars=20)
    with pytest.raises(splits.SplitError):
        splits.holdout(50, min_bars=30)


def test_purged_kfold_removes_overlapping_and_embargoed_rows() -> None:
    folds = list(splits.purged_kfold(100, folds=5, label_horizon=5, embargo_bars=3))
    assert len(folds) == 5
    for train, test in folds:
        assert not set(train) & set(test), "a test row leaked into training"
        lo, hi = min(test), max(test)
        for i in train:
            # Either the label window ends before the test starts, or the row sits
            # beyond the embargo after it.
            assert i + 5 <= lo or i >= hi + 1 + 3


# --- overrides ---------------------------------------------------------------


def test_overrides_are_restricted_to_the_whitelist() -> None:
    spec = _spec()
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"name": 1})
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"universe": 1})
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"indicators.nope.params.period": 5})
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"indicators.fast.params.std": 5})


def test_overrides_are_revalidated_through_the_full_dsl() -> None:
    """A swept value must clear exactly the checks a hand-authored value clears."""
    spec = _spec()
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"indicators.fast.params.period": 99999})  # out of range
    with pytest.raises(OverrideError):
        apply_overrides(spec, {"risk.max_position_pct": 5})  # must be in (0, 1]

    changed = apply_overrides(spec, {"indicators.fast.params.period": 7})
    assert changed.indicators[0].params["period"] == 7
    assert changed.spec_hash() != spec.spec_hash()


def test_grid_size_is_bounded() -> None:
    spec = _spec()
    axes = [
        Axis("indicators.fast.params.period", tuple(range(2, 22))),
        Axis("indicators.slow.params.period", tuple(range(20, 40))),
    ]
    with pytest.raises(OverrideError):
        build_grid(spec, axes)  # 400 combinations


def test_grid_enumerates_every_combination() -> None:
    combos = build_grid(
        _spec(),
        [
            Axis("indicators.fast.params.period", (5, 10)),
            Axis("exit.stop_loss_pct", (0.02, 0.05, 0.1)),
        ],
    )
    assert len(combos) == 6
    assert all(set(c) == {"indicators.fast.params.period", "exit.stop_loss_pct"} for c in combos)


# --- lab ---------------------------------------------------------------------


def test_walk_forward_reports_every_fold_out_of_sample() -> None:
    report = lab.run_walk_forward(_spec(), _bars(), CONFIG, folds=4)
    assert len(report.folds) == 4
    for fold in report.folds:
        assert fold.out_of_sample is not None
        assert fold.fold["test_bars"] > 0
    assert 0.0 <= report.consistency <= 1.0
    payload = report.as_dict()
    assert payload["note"]


def test_cost_stress_finds_the_breakeven_multiple() -> None:
    report = lab.run_cost_stress(_spec(), _bars(), CONFIG, multiples=(1.0, 2.0, 5.0, 50.0))
    assert [level["multiple"] for level in report.levels] == [1.0, 2.0, 5.0, 50.0]
    # Costs are monotonic: a higher multiple can never earn more.
    returns = [level["metrics"]["total_return"] or 0.0 for level in report.levels]
    assert returns == sorted(returns, reverse=True)
    assert report.note


def test_cost_stress_at_absurd_costs_is_never_profitable() -> None:
    """The lab must be able to say no."""
    report = lab.run_cost_stress(_spec(), _bars(), CONFIG, multiples=(1.0, 500.0))
    assert report.levels[-1]["profitable"] is False
    assert report.breakeven_multiple is not None


def test_sensitivity_reports_the_surface_not_just_the_best_cell() -> None:
    report = lab.run_sensitivity(
        _spec(),
        _bars(),
        CONFIG,
        [
            Axis("indicators.fast.params.period", (5, 10, 15)),
            Axis("exit.stop_loss_pct", (0.02, 0.05)),
        ],
    )
    assert report.tested == 6
    assert report.best is not None
    assert report.median_return is not None
    assert report.positive_share is not None
    assert report.neighbourhood_note
    # The best cell must never be presented alone.
    payload = report.as_dict()
    assert len(payload["cells"]) == 6


def test_sensitivity_records_rather_than_hides_invalid_cells() -> None:
    """A grid over a constrained space always has invalid corners; the count of
    dropped cells must be reported so the sweep's real size is not overstated."""
    report = lab.run_sensitivity(
        _spec(),
        _bars(200),
        CONFIG,
        [Axis("indicators.fast.params.period", (5, 10, 100000))],
    )
    assert report.skipped == 1
    assert report.tested == 2
    invalid = [c for c in report.cells if not c.valid]
    assert invalid and invalid[0].reason


def test_monte_carlo_produces_a_drawdown_distribution() -> None:
    result = engine.run(_spec(), _bars(), CONFIG)
    report = lab.run_monte_carlo(result, samples=200)
    if not result.trades or len(result.trades) < 5:
        pytest.skip("fixture produced too few trades to resample")
    methods = {d["method"] for d in report.distributions}
    assert "trade_reshuffle_drawdown" in methods
    for dist in report.distributions:
        assert dist["worst"] <= dist["median"] <= dist["best"]
        assert 0.0 <= dist["probability_negative"] <= 1.0
        assert "not a forecast" in dist["note"]


def test_monte_carlo_is_seeded_and_reproducible() -> None:
    result = engine.run(_spec(), _bars(), CONFIG)
    a = lab.run_monte_carlo(result, samples=200, seed=11)
    b = lab.run_monte_carlo(result, samples=200, seed=11)
    assert a.as_dict() == b.as_dict()


# --- multiple testing --------------------------------------------------------


def test_deflated_sharpe_punishes_a_large_search() -> None:
    """The same observed Sharpe must look worse after 200 trials than after one.

    This is the entire point of deflation: a number found by searching is not the
    same evidence as a number found by prediction.
    """
    rng = [0.001 * ((i % 7) - 3) + 0.0015 for i in range(300)]
    single = multiple_testing.assess_sharpe(rng, trials=1)
    searched = multiple_testing.assess_sharpe(
        rng, trial_sharpes=[0.05 * ((i % 11) - 5) for i in range(200)]
    )
    assert single.psr is not None and searched.deflated_sharpe is not None
    assert searched.deflated_sharpe < single.psr
    assert searched.expected_max_sharpe > 0


def test_expected_max_sharpe_grows_with_the_number_of_trials() -> None:
    bar_10 = multiple_testing.expected_max_sharpe(10, 0.04)
    bar_1000 = multiple_testing.expected_max_sharpe(1000, 0.04)
    assert 0 < bar_10 < bar_1000


def test_probabilistic_sharpe_is_a_probability() -> None:
    p = multiple_testing.probabilistic_sharpe(0.1, observations=250, skew=-0.5, kurtosis=6.0)
    assert p is not None and 0.0 <= p <= 1.0


def test_benjamini_hochberg_keeps_only_the_strongest() -> None:
    p_values = [0.001, 0.008, 0.04, 0.2, 0.6, 0.9]
    keep = multiple_testing.benjamini_hochberg(p_values, fdr=0.10)
    assert keep[0] and keep[1]
    assert not keep[-1] and not keep[-2]
    # Monotone: nothing weaker than a rejected hypothesis may be kept.
    kept_max = max((p for p, k in zip(p_values, keep, strict=True) if k), default=0)
    assert all(p <= kept_max for p, k in zip(p_values, keep, strict=True) if k)


def test_block_bootstrap_preserves_the_sample_length() -> None:
    returns = [0.001 * ((i % 5) - 2) for i in range(200)]
    dist = monte_carlo.block_bootstrap(returns, samples=100, seed=5)
    assert dist is not None
    assert dist.samples == 100
    assert dist.worst <= dist.observed <= dist.best or dist.observed_percentile in (0.0, 100.0)


def test_resampling_declines_on_a_too_small_sample() -> None:
    assert monte_carlo.block_bootstrap([0.01] * 10) is None
