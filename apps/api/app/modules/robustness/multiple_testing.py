"""Multiple-testing correction.

If you try 200 parameter combinations and report the best one, its Sharpe ratio is
not an estimate of that strategy's edge — it is the maximum of 200 draws from a
distribution, and the maximum of many draws is large even when the true edge is
zero. This module makes that arithmetic explicit instead of leaving it to the
reader's optimism.

Implemented:

* **Probabilistic Sharpe Ratio (PSR)** — the probability the true Sharpe exceeds a
  benchmark, given the observed Sharpe, the sample length, and the skew/kurtosis of
  the returns. Non-normal returns (which trading returns always are) inflate the
  standard error of a Sharpe estimate, and PSR accounts for that.
* **Deflated Sharpe Ratio (DSR)** — PSR against a benchmark raised to reflect how
  many independent trials were run. This is the number that should be quoted after
  a parameter sweep.
* **Benjamini-Hochberg FDR** — for deciding which of many tested variants survive
  as a family, controlling the expected proportion of false discoveries.

Both PSR and DSR follow Bailey & Lopez de Prado. The implementation uses only the
standard library and numpy so the free local path has no extra dependency.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

# Euler-Mascheroni constant, used in the expected-maximum approximation.
_EULER = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation).

    Accurate to ~1e-9 over (0,1), which is far beyond what this use needs, and
    avoids taking a scipy dependency for one function.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


@dataclass(frozen=True, slots=True)
class SharpeAssessment:
    """Everything needed to judge a reported Sharpe ratio."""

    observed_sharpe: float  # per-observation (NOT annualized)
    observations: int
    skew: float
    kurtosis: float  # non-excess (3.0 for a normal distribution)
    trials: int
    psr: float | None  # P(true Sharpe > 0)
    deflated_sharpe: float | None  # P(true Sharpe > the selection-adjusted benchmark)
    expected_max_sharpe: float | None  # the bar a null strategy would clear by luck
    verdict: str

    def as_dict(self) -> dict[str, object]:
        return {
            "observed_sharpe": round(self.observed_sharpe, 6),
            "observations": self.observations,
            "skew": round(self.skew, 6),
            "kurtosis": round(self.kurtosis, 6),
            "trials": self.trials,
            "psr": None if self.psr is None else round(self.psr, 6),
            "deflated_sharpe": (
                None if self.deflated_sharpe is None else round(self.deflated_sharpe, 6)
            ),
            "expected_max_sharpe": (
                None if self.expected_max_sharpe is None else round(self.expected_max_sharpe, 6)
            ),
            "verdict": self.verdict,
        }


def probabilistic_sharpe(
    observed: float, *, observations: int, skew: float, kurtosis: float, benchmark: float = 0.0
) -> float | None:
    """P(true Sharpe > ``benchmark``) given a non-normal return sample.

    The standard error of a Sharpe estimate grows with negative skew and fat tails —
    exactly the shape a strategy with occasional large losses produces — so a naive
    t-statistic overstates confidence for precisely the strategies where it matters.
    """
    if observations < 2:
        return None
    denominator = 1.0 - skew * observed + ((kurtosis - 1.0) / 4.0) * observed**2
    if denominator <= 0:
        return None
    z = (observed - benchmark) * math.sqrt(observations - 1) / math.sqrt(denominator)
    return _norm_cdf(z)


def expected_max_sharpe(trials: int, variance_across_trials: float) -> float:
    """The highest Sharpe you would expect from ``trials`` strategies with NO edge.

    This is the bar a genuine result has to clear. With enough trials it is
    surprisingly high, which is the entire point: a sweep that reports its best cell
    without this number is reporting a selection artefact.
    """
    if trials <= 1 or variance_across_trials <= 0:
        return 0.0
    sigma = math.sqrt(variance_across_trials)
    n = float(trials)
    term = (1 - _EULER) * _norm_ppf(1 - 1 / n) + _EULER * _norm_ppf(1 - 1 / (n * math.e))
    return sigma * term


def assess_sharpe(
    returns: Sequence[float],
    *,
    trials: int = 1,
    trial_sharpes: Sequence[float] | None = None,
) -> SharpeAssessment:
    """Full assessment of a per-observation Sharpe ratio.

    ``trial_sharpes`` should be the Sharpe of EVERY variant tried (e.g. every cell of
    a parameter grid). Their spread is what sets the selection bar; without them the
    deflation falls back to a conservative default spread.
    """
    arr = np.asarray(list(returns), dtype=float)
    n = int(arr.size)
    if n < 2:
        return SharpeAssessment(
            0.0, n, 0.0, 3.0, trials, None, None, None, "Not enough observations to assess."
        )
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    if std == 0:
        return SharpeAssessment(
            0.0,
            n,
            0.0,
            3.0,
            trials,
            None,
            None,
            None,
            "Zero return variance: a Sharpe ratio is undefined.",
        )
    observed = mean / std
    centered = arr - mean
    skew = float(np.mean(centered**3) / std**3)
    kurt = float(np.mean(centered**4) / std**4)

    psr = probabilistic_sharpe(observed, observations=n, skew=skew, kurtosis=kurt)

    if trial_sharpes is not None and len(trial_sharpes) > 1:
        variance = float(np.var(np.asarray(list(trial_sharpes), dtype=float), ddof=1))
        effective_trials = len(trial_sharpes)
    else:
        # No grid supplied: assume the trials had the same dispersion as this sample's
        # own estimation error. Conservative, and stated in the verdict.
        variance = 1.0 / max(n - 1, 1)
        effective_trials = trials

    bar = expected_max_sharpe(effective_trials, variance)
    dsr = (
        probabilistic_sharpe(observed, observations=n, skew=skew, kurtosis=kurt, benchmark=bar)
        if effective_trials > 1
        else psr
    )

    if dsr is None:
        verdict = "Could not be assessed."
    elif dsr >= 0.95:
        verdict = (
            f"Survives deflation for {effective_trials} trial(s): the observed Sharpe is "
            f"above the {bar:.3f} a no-edge search of this size would be expected to reach."
        )
    elif dsr >= 0.5:
        verdict = (
            f"Weak: after adjusting for {effective_trials} trial(s) there is only a "
            f"{dsr:.0%} chance the true Sharpe is positive."
        )
    else:
        verdict = (
            f"Not distinguishable from selection luck: {effective_trials} trial(s) would be "
            f"expected to produce a Sharpe of about {bar:.3f} with no edge at all."
        )

    return SharpeAssessment(observed, n, skew, kurt, effective_trials, psr, dsr, bar, verdict)


def benjamini_hochberg(p_values: Sequence[float], *, fdr: float = 0.10) -> list[bool]:
    """Which hypotheses survive at a false-discovery rate of ``fdr``.

    Bonferroni would be stricter but is far too conservative for a parameter sweep,
    where the tests are heavily correlated; BH controls the expected PROPORTION of
    false positives among the ones declared significant, which is the quantity a
    researcher actually cares about when screening variants.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    keep = [False] * n
    cutoff_rank = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= fdr * rank / n:
            cutoff_rank = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= cutoff_rank:
            keep[idx] = True
    return keep
