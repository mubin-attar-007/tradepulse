"""Robustness endpoints (auth-gated, owner-scoped).

Runs synchronously: a suite over a few thousand bars completes in well under a
second per analysis on this engine, and a synchronous result is far easier to reason
about than a job id. The seam to move it onto the existing ARQ worker is the same one
paper trading already uses, and is taken when a run is measurably slow rather than
pre-emptively.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import SessionDep
from app.core.errors import BadRequestError, NotFoundError
from app.modules.auth.deps import CurrentUser
from app.modules.experiments.repository import ExperimentRepository
from app.modules.robustness.overrides import MAX_AXES, MAX_VALUES_PER_AXIS, Axis, OverrideError
from app.modules.robustness.service import RobustnessService

router = APIRouter(prefix="/robustness", tags=["robustness"])
experiments_router = APIRouter(prefix="/experiments", tags=["experiments"])


class AxisIn(BaseModel):
    """One swept parameter. ``path`` must address a whitelisted numeric leaf."""

    path: str = Field(
        max_length=120,
        description=(
            "A sweepable parameter, e.g. 'indicators.<id>.params.period', "
            "'exit.stop_loss_pct', 'sizing.value', 'risk.max_position_pct'."
        ),
    )
    values: list[float] = Field(min_length=1, max_length=MAX_VALUES_PER_AXIS)


class RobustnessSuiteRequest(BaseModel):
    strategy_id: uuid.UUID
    start: datetime
    end: datetime
    hypothesis: str | None = Field(default=None, max_length=2000)
    folds: int = Field(default=4, ge=2, le=10)
    anchored: bool = True
    embargo_bars: int = Field(default=0, ge=0, le=500)
    axes: list[AxisIn] = Field(default_factory=list, max_length=MAX_AXES)
    cost_multiples: list[float] = Field(
        default_factory=lambda: [1.0, 1.5, 2.0, 3.0, 5.0], min_length=1, max_length=10
    )
    monte_carlo_samples: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=7, ge=0, le=2**31 - 1)


class ExperimentOut(BaseModel):
    """A persisted experiment, carrying its own provenance."""

    id: uuid.UUID
    kind: str
    status: str
    title: str
    hypothesis: str | None
    strategy_id: uuid.UUID | None
    strategy_version: int | None
    spec_hash: str
    symbol: str | None
    timeframe: str | None
    start_ts: datetime | None
    end_ts: datetime | None
    data_fingerprint: str
    bars: int | None
    engine_version: str
    metrics_version: str
    cost_model_version: str
    seed: int | None
    config: dict | None
    result: dict | None
    error: str | None
    error_category: str | None
    parent_id: uuid.UUID | None
    tags: list[str] | None
    notes: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ExperimentSummaryOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    title: str
    symbol: str | None
    timeframe: str | None
    spec_hash: str
    data_fingerprint: str
    created_at: datetime
    completed_at: datetime | None
    # Surfaced on the list so a researcher can see the verdict without opening each row.
    verdict: str | None = None

    model_config = {"from_attributes": True}


@router.post("/suite", status_code=201, response_model=ExperimentOut)
async def run_robustness_suite(
    payload: RobustnessSuiteRequest, session: SessionDep, user: CurrentUser
) -> ExperimentOut:
    """Run walk-forward, cost stress, resampling and (optionally) a parameter sweep,
    then return a stability verdict with the evidence behind every check."""
    if payload.start >= payload.end:
        raise BadRequestError("`start` must be before `end`.")
    try:
        axes = tuple(Axis(path=a.path, values=tuple(a.values)) for a in payload.axes)
    except Exception as exc:  # pragma: no cover - pydantic already constrains shape
        raise BadRequestError(str(exc)) from exc

    service = RobustnessService(session, user.id)
    try:
        experiment = await service.run_suite(
            payload.strategy_id,
            start=payload.start,
            end=payload.end,
            folds=payload.folds,
            anchored=payload.anchored,
            embargo_bars=payload.embargo_bars,
            axes=axes,
            cost_multiples=payload.cost_multiples,
            monte_carlo_samples=payload.monte_carlo_samples,
            seed=payload.seed,
            hypothesis=payload.hypothesis,
        )
    except OverrideError as exc:
        raise BadRequestError(str(exc)) from exc
    return ExperimentOut.model_validate(experiment)


@experiments_router.get("", response_model=list[ExperimentSummaryOut])
async def list_experiments(
    session: SessionDep,
    user: CurrentUser,
    kind: str | None = Query(default=None),
    strategy_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExperimentSummaryOut]:
    rows = await ExperimentRepository(session, user.id).list_for_owner(
        kind=kind, strategy_id=strategy_id, limit=limit
    )
    out: list[ExperimentSummaryOut] = []
    for row in rows:
        summary = ExperimentSummaryOut.model_validate(row)
        result = row.result or {}
        stability = result.get("stability") if isinstance(result, dict) else None
        if isinstance(stability, dict):
            summary.verdict = stability.get("verdict")
        out.append(summary)
    return out


@experiments_router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ExperimentOut:
    experiment = await ExperimentRepository(session, user.id).get(experiment_id)
    if experiment is None:
        raise NotFoundError()
    return ExperimentOut.model_validate(experiment)
