"""Time-series data splits.

Every split here obeys one rule: **the evaluation window is strictly later than the
window used to choose anything**. Random k-fold, the default in general ML, is
invalid on a time series precisely because it breaks that rule — and it breaks it
invisibly, producing excellent scores from a model that has read the future.

Two subtler leaks are handled explicitly:

* **Label overlap.** If a label at time t depends on the following h bars, then a
  training row at t and a test row at t+1 share h-1 bars of outcome. The fold is
  therefore *purged*: training rows whose label window overlaps the test window are
  dropped.
* **Serial correlation at the boundary.** Even without label overlap, adjacent bars
  are correlated, so a training row immediately before the test window leaks
  through autocorrelation. An *embargo* discards a gap after each test window.

Both come from Lopez de Prado's treatment of purging and embargoing; they are
implemented on bar INDICES, so they apply equally to a strategy backtest and to a
supervised dataset.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Fold:
    """One train/test pair, expressed as half-open bar-index ranges."""

    index: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive
    label: str = ""

    @property
    def train_size(self) -> int:
        return max(0, self.train_end - self.train_start)

    @property
    def test_size(self) -> int:
        return max(0, self.test_end - self.test_start)

    def describe(self, timestamps: Sequence[datetime] | None = None) -> dict[str, object]:
        out: dict[str, object] = {
            "index": self.index,
            "label": self.label,
            "train_bars": self.train_size,
            "test_bars": self.test_size,
        }
        if timestamps:
            out["train_start"] = timestamps[self.train_start].isoformat()
            out["train_end"] = timestamps[self.train_end - 1].isoformat()
            out["test_start"] = timestamps[self.test_start].isoformat()
            out["test_end"] = timestamps[self.test_end - 1].isoformat()
        return out


class SplitError(ValueError):
    """A split that cannot be produced from the data provided.

    Raised loudly rather than silently returning fewer folds: "we quietly ran 2 of
    the 6 folds you asked for" is how an out-of-sample claim becomes untrue.
    """


def holdout(
    n_bars: int, *, train: float = 0.6, validation: float = 0.2, min_bars: int = 30
) -> tuple[Fold, Fold]:
    """A single train / validation / test partition in chronological order.

    Returns (train->validation, train+validation->test). The final test segment is
    the untouched holdout: it must be looked at once, at the end, or it stops being
    a holdout.
    """
    if not 0 < train < 1 or not 0 < validation < 1 or train + validation >= 1:
        raise SplitError("train and validation must be fractions in (0,1) summing to < 1")
    train_end = int(n_bars * train)
    val_end = int(n_bars * (train + validation))
    if min(train_end, val_end - train_end, n_bars - val_end) < min_bars:
        raise SplitError(
            f"{n_bars} bars cannot produce three segments of at least {min_bars} bars "
            f"at train={train}, validation={validation}"
        )
    return (
        Fold(0, 0, train_end, train_end, val_end, label="validation"),
        Fold(1, 0, val_end, val_end, n_bars, label="test"),
    )


def walk_forward(
    n_bars: int,
    *,
    folds: int = 5,
    train_bars: int | None = None,
    test_bars: int | None = None,
    anchored: bool = True,
    embargo_bars: int = 0,
    min_train_bars: int = 30,
    min_test_bars: int = 10,
) -> list[Fold]:
    """Rolling out-of-sample evaluation.

    ``anchored=True`` grows the training window from a fixed origin (an expanding
    window: more data each step, closest to how a strategy would actually be
    re-fitted in production). ``anchored=False`` slides a fixed-length window, which
    answers a different question — whether the edge is stable in RECENT data rather
    than whether it survives being averaged over all history.
    """
    if folds < 1:
        raise SplitError("folds must be >= 1")
    if test_bars is None:
        usable = n_bars - (train_bars or min_train_bars)
        test_bars = max(usable // folds, 0)
    if train_bars is None:
        train_bars = n_bars - folds * test_bars
    if train_bars < min_train_bars or test_bars < min_test_bars:
        raise SplitError(
            f"{n_bars} bars cannot support {folds} folds of {test_bars} test bars after a "
            f"{train_bars}-bar training window (minimums: {min_train_bars}/{min_test_bars}). "
            "Backfill more history or ask for fewer folds."
        )

    out: list[Fold] = []
    for k in range(folds):
        test_start = train_bars + k * test_bars
        test_end = min(test_start + test_bars, n_bars)
        if test_end - test_start < min_test_bars:
            break
        train_start = 0 if anchored else max(0, test_start - train_bars - embargo_bars)
        train_end = max(train_start, test_start - embargo_bars)
        if train_end - train_start < min_train_bars:
            break
        out.append(
            Fold(
                index=k,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                label=f"fold {k + 1}",
            )
        )
    if len(out) < folds:
        # Returning 2 of the 5 folds a caller asked for would make an out-of-sample
        # claim quietly untrue — the report would say "walk-forward over 5 folds"
        # while covering a fraction of the intended period. Fail loudly instead.
        raise SplitError(
            f"{n_bars} bars produced only {len(out)} of the {folds} requested folds at "
            f"train={train_bars}, test={test_bars}. Reduce the fold count, shorten the "
            "training window, or backfill more history."
        )
    return out


def purged_kfold(
    n_bars: int,
    *,
    folds: int = 5,
    label_horizon: int = 1,
    embargo_bars: int = 0,
) -> Iterator[tuple[list[int], list[int]]]:
    """Purged, embargoed k-fold over bar indices — for SUPERVISED datasets.

    Yields ``(train_indices, test_indices)``. Unlike walk-forward, test folds here
    may sit anywhere in the series (which is legitimate for cross-sectional model
    evaluation), so leakage prevention has to be explicit:

    * a training index is PURGED if its label window ``[i, i + label_horizon)``
      overlaps the test window at all;
    * a further ``embargo_bars`` immediately after each test window are dropped, to
      cut the autocorrelation bridge between test and subsequent training rows.
    """
    if folds < 2:
        raise SplitError("purged k-fold needs at least 2 folds")
    if label_horizon < 1:
        raise SplitError("label_horizon must be >= 1")
    fold_size = n_bars // folds
    if fold_size < 1:
        raise SplitError(f"{n_bars} bars cannot be split into {folds} folds")

    for k in range(folds):
        test_start = k * fold_size
        test_end = n_bars if k == folds - 1 else (k + 1) * fold_size
        test = list(range(test_start, test_end))

        embargo_end = min(n_bars, test_end + embargo_bars)
        train = [
            i
            for i in range(n_bars)
            # Purge: the row's own label window must not touch the test window.
            if (i + label_horizon <= test_start or i >= embargo_end)
        ]
        yield train, test


def describe_splits(folds: Sequence[Fold], timestamps: Sequence[datetime] | None = None) -> list:
    return [f.describe(timestamps) for f in folds]
