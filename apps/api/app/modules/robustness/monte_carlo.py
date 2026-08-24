"""Monte Carlo resampling of a completed run.

The question these answer is narrow and worth stating precisely: **given the trades
this strategy actually produced, how much of the final outcome was the ORDER they
arrived in rather than their average quality?** A strategy whose drawdown depends
on the lucky ordering of a handful of winners is fragile even if its total return
looks fine.

What this is NOT: a forecast. Every method here resamples the strategy's own
realized history, so it inherits that history's regime, its instrument, and its
sample size. It cannot tell you what the market will do next, and the report says
so wherever these numbers appear.

Three methods, because they break different assumptions:

* ``reshuffle_trades``  — permutes trade order. Breaks sequence dependence, keeps
                          the exact multiset of outcomes.
* ``block_bootstrap``   — resamples CONTIGUOUS blocks of bar returns, preserving
                          short-range autocorrelation and volatility clustering
                          that an i.i.d. bootstrap would destroy.
* ``perturb_costs``     — charges extra round-trip friction against each realized
                          trade. A cheap first-order check; the full cost-stress
                          sweep in :mod:`app.modules.robustness.lab` re-runs the
                          engine instead, because higher costs also change WHICH
                          trades are taken.

Start-date perturbation is NOT implemented. It belongs here and is listed in the
roadmap; it is called out explicitly so this list cannot be read as a claim.

All methods are seeded, so a reported distribution is reproducible.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.modules.backtesting.types import Trade


@dataclass(frozen=True, slots=True)
class Distribution:
    """Summary of a resampled outcome distribution."""

    method: str
    samples: int
    seed: int
    median: float
    mean: float
    p05: float
    p25: float
    p75: float
    p95: float
    worst: float
    best: float
    probability_negative: float
    observed: float
    observed_percentile: float
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "samples": self.samples,
            "seed": self.seed,
            "median": round(self.median, 8),
            "mean": round(self.mean, 8),
            "p05": round(self.p05, 8),
            "p25": round(self.p25, 8),
            "p75": round(self.p75, 8),
            "p95": round(self.p95, 8),
            "worst": round(self.worst, 8),
            "best": round(self.best, 8),
            "probability_negative": round(self.probability_negative, 6),
            "observed": round(self.observed, 8),
            "observed_percentile": round(self.observed_percentile, 4),
            "note": self.note,
        }


_NOTE = (
    "Resampled from this run's own realized history. It measures sequence and "
    "sampling luck WITHIN the tested period; it is not a forecast and carries no "
    "information about future markets."
)


def _summarize(
    method: str, values: np.ndarray, observed: float, seed: int, note: str = _NOTE
) -> Distribution:
    percentile = float((values < observed).mean() * 100.0) if values.size else 0.0
    return Distribution(
        method=method,
        samples=int(values.size),
        seed=seed,
        median=float(np.median(values)),
        mean=float(np.mean(values)),
        p05=float(np.percentile(values, 5)),
        p25=float(np.percentile(values, 25)),
        p75=float(np.percentile(values, 75)),
        p95=float(np.percentile(values, 95)),
        worst=float(np.min(values)),
        best=float(np.max(values)),
        probability_negative=float((values < 0).mean()),
        observed=observed,
        observed_percentile=percentile,
        note=note,
    )


def _equity_path(returns: np.ndarray) -> np.ndarray:
    return np.cumprod(1.0 + returns)


def _max_drawdown(path: np.ndarray) -> float:
    peak = np.maximum.accumulate(path)
    return float(np.min(path / peak - 1.0))


def reshuffle_trades(
    trades: Sequence[Trade], *, samples: int = 1000, seed: int = 7
) -> tuple[Distribution, Distribution] | None:
    """Permute trade ORDER and re-accumulate.

    Total compounded return varies only slightly under permutation (multiplication
    commutes), so the informative output is the DRAWDOWN distribution: the same
    trades in an unlucky order can produce a far deeper drawdown than the one that
    happened to occur, and that is the number a position-sizing decision depends on.
    """
    rets = np.array([t.return_pct for t in trades], dtype=float)
    if rets.size < 5:
        return None
    rng = np.random.default_rng(seed)

    finals = np.empty(samples)
    drawdowns = np.empty(samples)
    for i in range(samples):
        shuffled = rng.permutation(rets)
        path = _equity_path(shuffled)
        finals[i] = path[-1] - 1.0
        drawdowns[i] = _max_drawdown(path)

    observed_path = _equity_path(rets)
    return (
        _summarize("trade_reshuffle_return", finals, float(observed_path[-1] - 1.0), seed),
        _summarize("trade_reshuffle_drawdown", drawdowns, _max_drawdown(observed_path), seed),
    )


def block_bootstrap(
    bar_returns: Sequence[float],
    *,
    samples: int = 1000,
    block_size: int | None = None,
    seed: int = 7,
) -> Distribution | None:
    """Resample contiguous BLOCKS of per-bar returns.

    An i.i.d. bootstrap would shatter volatility clustering — the property that
    turbulent bars arrive together — and so would systematically understate
    drawdown. Blocks preserve it up to their own length. The default block length
    follows the common n^(1/3) rule of thumb.
    """
    rets = np.asarray(list(bar_returns), dtype=float)
    n = rets.size
    if n < 30:
        return None
    if block_size is None:
        block_size = max(2, round(n ** (1 / 3)))
    block_size = min(block_size, n)
    n_blocks = math.ceil(n / block_size)
    rng = np.random.default_rng(seed)

    finals = np.empty(samples)
    for i in range(samples):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        drawn = np.concatenate([rets[s : s + block_size] for s in starts])[:n]
        finals[i] = float(np.prod(1.0 + drawn) - 1.0)

    observed = float(np.prod(1.0 + rets) - 1.0)
    return _summarize(
        "block_bootstrap_return",
        finals,
        observed,
        seed,
        note=_NOTE + f" Block length {block_size} bars preserves short-range autocorrelation.",
    )


def perturb_costs(
    trades: Sequence[Trade],
    *,
    initial_equity: float,
    extra_cost_bps: Sequence[float] = (0.0, 2.0, 5.0, 10.0, 25.0),
) -> list[dict[str, float | bool | None]]:
    """Charge additional round-trip friction against each realized trade.

    A cheap first-order stress: it does not re-run the strategy (so it cannot show
    trades that would no longer be taken), which is exactly why the full cost-stress
    sweep re-runs the engine instead. This one is useful for showing, instantly, how
    thin the margin is.
    """
    out = []
    for bps in extra_cost_bps:
        drag = bps / 10000.0
        total = 0.0
        for t in trades:
            notional = float(t.qty) * float(t.entry_price)
            total += float(t.pnl) - notional * drag * 2  # both legs
        out.append(
            {
                "extra_bps_per_side": bps,
                "net_pnl": round(total, 6),
                "return_on_initial": round(total / initial_equity, 8) if initial_equity else None,
                "still_profitable": total > 0,
            }
        )
    return out
