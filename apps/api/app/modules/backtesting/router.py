"""Backtest endpoints (auth-gated, owner-scoped). Runs synchronously for MVP."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.errors import NotFoundError
from app.modules.auth.deps import CurrentUser
from app.modules.backtesting.orchestration import BacktestService
from app.modules.backtesting.repository import BacktestRepository
from app.modules.backtesting.schemas import (
    BacktestOut,
    BacktestSummaryOut,
    CreateBacktestRequest,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", status_code=201, response_model=BacktestOut)
async def create_backtest(
    payload: CreateBacktestRequest, session: SessionDep, user: CurrentUser
) -> BacktestOut:
    backtest = await BacktestService(session, user.id).run(
        payload.strategy_id, payload.start, payload.end
    )
    return BacktestOut.model_validate(backtest)


@router.get("", response_model=list[BacktestSummaryOut])
async def list_backtests(session: SessionDep, user: CurrentUser) -> list[BacktestSummaryOut]:
    rows = await BacktestRepository(session, user.id).list_for_owner()
    return [BacktestSummaryOut.model_validate(row) for row in rows]


@router.get("/{backtest_id}", response_model=BacktestOut)
async def get_backtest(
    backtest_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> BacktestOut:
    backtest = await BacktestRepository(session, user.id).get(backtest_id)
    if backtest is None:
        raise NotFoundError()
    return BacktestOut.model_validate(backtest)
