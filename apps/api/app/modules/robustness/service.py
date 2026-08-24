"""Robustness orchestration: load data, run the analyses, persist the evidence.

Everything an analysis needs to be reproducible is captured at the moment it runs —
the strategy version, the data fingerprint, the engine/metric/cost-model versions,
the seed, and the analysis configuration — and written into an append-only
Experiment row. A result that cannot be traced back to those inputs is not evidence,
it is an anecdote.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.backtesting import engine
from app.modules.backtesting.metrics import METRICS_VERSION
from app.modules.backtesting.service import data_fingerprint
from app.modules.backtesting.types import COST_MODEL_VERSION, BacktestResult, ExecutionConfig
from app.modules.experiments.models import Experiment
from app.modules.experiments.repository import ExperimentRepository, count_trials
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.market_data.repository import BarPoint
from app.modules.robustness import lab, stability
from app.modules.robustness.overrides import Axis, OverrideError, build_grid
from app.modules.robustness.splits import SplitError
from app.modules.strategies.repository import StrategyRepository, StrategyVersionRepository
from app.modules.strategies.spec import ENGINE_VERSION, StrategySpec

logger = get_logger("robustness")

# A robustness suite re-runs the engine many times. These bounds keep one request
# from monopolising the process, and are reported with the result so a truncated
# analysis is never mistaken for a complete one.
MIN_BARS_FOR_ROBUSTNESS = 120
MAX_MONTE_CARLO_SAMPLES = 5000


class RobustnessService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.experiments = ExperimentRepository(session, owner_id)

    async def _load(
        self, strategy_id: uuid.UUID, start: datetime, end: datetime
    ) -> tuple[StrategySpec, int, Instrument, list[BarPoint]]:
        strategy = await StrategyRepository(self.session, self.owner_id).get(strategy_id)
        if strategy is None:
            raise NotFoundError()
        version = await StrategyVersionRepository(self.session, self.owner_id).latest(strategy_id)
        if version is None:
            raise BadRequestError("Strategy has no version to analyse.")
        spec = StrategySpec.model_validate(version.spec)

        symbol = spec.universe[0]
        instrument = await self.session.scalar(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        if instrument is None:
            raise NotFoundError(f"Unknown instrument {symbol!r}; seed it and backfill first.")

        bars = await md_repo.get_bars(
            self.session, instrument.id, timeframe=spec.timeframe, start=start, end=end
        )
        if len(bars) < MIN_BARS_FOR_ROBUSTNESS:
            raise BadRequestError(
                f"Robustness analysis needs at least {MIN_BARS_FOR_ROBUSTNESS} closed "
                f"{spec.timeframe} bars; this window has {len(bars)}. Splitting a shorter "
                "series into out-of-sample folds would produce segments too small to mean "
                "anything. Backfill more history or widen the window."
            )
        return spec, version.version, instrument, bars

    def _new_experiment(
        self,
        *,
        kind: str,
        title: str,
        spec: StrategySpec,
        strategy_id: uuid.UUID,
        strategy_version: int,
        instrument: Instrument,
        bars: Sequence[BarPoint],
        start: datetime,
        end: datetime,
        config: ExecutionConfig,
        analysis: dict[str, object],
        seed: int | None = None,
    ) -> Experiment:
        return Experiment(
            kind=kind,
            status="running",
            title=title,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            spec=spec.model_dump(mode="json"),
            spec_hash=spec.spec_hash(),
            symbol=instrument.symbol,
            timeframe=spec.timeframe,
            start_ts=start,
            end_ts=end,
            data_fingerprint=data_fingerprint(instrument.id, spec.timeframe, bars),
            bars=len(bars),
            engine_version=ENGINE_VERSION,
            metrics_version=METRICS_VERSION,
            cost_model_version=COST_MODEL_VERSION,
            seed=seed,
            config={"execution": config.as_dict(), "analysis": analysis},
        )

    async def _finish(
        self, experiment: Experiment, result: dict[str, object] | None, error: Exception | None
    ) -> Experiment:
        if error is None:
            experiment.status = "done"
            experiment.result = result
        else:
            experiment.status = "failed"
            experiment.error = str(error)[:500]
            experiment.error_category = type(error).__name__
        experiment.completed_at = datetime.now(UTC)
        await self.experiments.add(experiment)
        await self.session.flush()
        return experiment

    async def run_suite(
        self,
        strategy_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
        config: ExecutionConfig | None = None,
        folds: int = 4,
        anchored: bool = True,
        embargo_bars: int = 0,
        axes: Sequence[Axis] = (),
        cost_multiples: Sequence[float] = (1.0, 1.5, 2.0, 3.0, 5.0),
        monte_carlo_samples: int = 1000,
        seed: int = 7,
        hypothesis: str | None = None,
    ) -> Experiment:
        """Run the full battery and persist one experiment carrying all of it.

        The analyses are stored together rather than as separate rows because the
        stability verdict is only meaningful over the whole set — a walk-forward
        result read without its cost stress invites exactly the selective reading the
        lab exists to prevent.
        """
        config = config or ExecutionConfig()
        samples = max(100, min(monte_carlo_samples, MAX_MONTE_CARLO_SAMPLES))
        spec, version, instrument, bars = await self._load(strategy_id, start, end)

        # Validate the sweep BEFORE spending any compute. A mistyped or
        # non-whitelisted parameter path is a request error the caller can fix, so it
        # must surface as one — not be buried as a "gap in the evidence" inside an
        # otherwise successful report, where it would be easy to miss.
        if axes:
            build_grid(spec, axes)

        experiment = self._new_experiment(
            kind="robustness_suite",
            title=f"Robustness suite — {spec.name}",
            spec=spec,
            strategy_id=strategy_id,
            strategy_version=version,
            instrument=instrument,
            bars=bars,
            start=start,
            end=end,
            config=config,
            analysis={
                "folds": folds,
                "anchored": anchored,
                "embargo_bars": embargo_bars,
                "axes": [{"path": a.path, "values": list(a.values)} for a in axes],
                "cost_multiples": list(cost_multiples),
                "monte_carlo_samples": samples,
            },
            seed=seed,
        )
        experiment.hypothesis = hypothesis

        # How many times this owner has already asked this exact question. Repeat
        # runs of the same spec are additional draws, and a correction that ignores
        # them flatters a result that was found by trying again.
        prior_trials = await count_trials(self.session, self.owner_id, spec.spec_hash())

        # Lineage: point a rerun at the earliest completed run of the same spec over
        # the same data, so the experiment list shows repeats AS repeats rather than
        # as independent confirmations of the same finding.
        siblings = await self.experiments.by_fingerprint(
            experiment.data_fingerprint, experiment.spec_hash
        )
        if siblings:
            experiment.parent_id = min(siblings, key=lambda e: e.created_at).id

        try:
            baseline: BacktestResult = engine.run(spec, bars, config, calendar=instrument.calendar)

            walk = None
            walk_error = None
            try:
                walk = lab.run_walk_forward(
                    spec,
                    bars,
                    config,
                    calendar=instrument.calendar,
                    folds=folds,
                    anchored=anchored,
                    embargo_bars=embargo_bars,
                )
            except SplitError as exc:
                # A split that cannot be honoured is reported as a gap in the evidence,
                # never silently skipped — "we could not test this" must be visible.
                walk_error = str(exc)

            sensitivity = None
            sensitivity_error = None
            if axes:
                try:
                    sensitivity = lab.run_sensitivity(
                        spec,
                        bars,
                        config,
                        axes,
                        calendar=instrument.calendar,
                        prior_trials=prior_trials,
                    )
                except OverrideError as exc:  # pragma: no cover - pre-validated above
                    sensitivity_error = str(exc)

            costs = lab.run_cost_stress(
                spec, bars, config, calendar=instrument.calendar, multiples=cost_multiples
            )
            mc = lab.run_monte_carlo(baseline, samples=samples, seed=seed)

            verdict = stability.assess(
                metrics=baseline.metrics,
                walk_forward=walk,
                sensitivity=sensitivity,
                cost_stress=costs,
                monte_carlo=mc,
            )

            payload: dict[str, object] = {
                "baseline": {
                    "metrics": baseline.metrics,
                    "num_trades": len(baseline.trades),
                    "final_equity": str(baseline.final_equity),
                    "total_commission": str(baseline.total_commission),
                    "bars": baseline.bars,
                },
                "walk_forward": walk.as_dict() if walk else None,
                "walk_forward_error": walk_error,
                "sensitivity": sensitivity.as_dict() if sensitivity else None,
                "sensitivity_error": sensitivity_error,
                "cost_stress": costs.as_dict(),
                "monte_carlo": mc.as_dict(),
                "stability": verdict.as_dict(),
                "disclosure": (
                    "Historical simulation under the displayed assumptions. Results are "
                    "hypothetical, are not achievable returns, and do not predict future "
                    "performance."
                ),
            }
            logger.info(
                "robustness_suite_done",
                strategy_id=str(strategy_id),
                verdict=verdict.verdict,
                bars=len(bars),
            )
            return await self._finish(experiment, payload, None)
        except (BadRequestError, NotFoundError):
            raise
        except Exception as exc:  # persist the failure rather than 500-ing
            logger.exception("robustness_suite_failed", strategy_id=str(strategy_id))
            return await self._finish(experiment, None, exc)
