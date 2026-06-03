"""Strategy CRUD + versioning endpoints (auth-gated, owner-scoped).

The request body is the canonical StrategySpec, so FastAPI/Pydantic enforces
the full DSL (mandatory exit/sizing/risk, closed catalog) at the edge — 422 on
anything the legacy's optimistic strategy would have been.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.errors import NotFoundError
from app.modules.auth.deps import CurrentUser
from app.modules.strategies import repository as repo
from app.modules.strategies.schemas import StrategyDetailOut, StrategyOut, StrategyVersionOut
from app.modules.strategies.service import StrategyService
from app.modules.strategies.spec import StrategySpec

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", status_code=201, response_model=StrategyDetailOut)
async def create_strategy(
    spec: StrategySpec, session: SessionDep, user: CurrentUser
) -> StrategyDetailOut:
    strategy, version = await StrategyService(session, user.id).create(spec)
    return StrategyDetailOut.build(strategy, version)


@router.get("", response_model=list[StrategyOut])
async def list_strategies(session: SessionDep, user: CurrentUser) -> list[StrategyOut]:
    rows = await repo.list_strategies(session, user.id)
    return [StrategyOut.model_validate(row) for row in rows]


@router.get("/{strategy_id}", response_model=StrategyDetailOut)
async def get_strategy(
    strategy_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> StrategyDetailOut:
    service = StrategyService(session, user.id)
    strategy = await service.strategies.get(strategy_id)
    if strategy is None:
        raise NotFoundError()
    latest = await service.versions.latest(strategy_id)
    return StrategyDetailOut.build(strategy, latest)


@router.post("/{strategy_id}/versions", status_code=201, response_model=StrategyVersionOut)
async def add_version(
    strategy_id: uuid.UUID, spec: StrategySpec, session: SessionDep, user: CurrentUser
) -> StrategyVersionOut:
    version = await StrategyService(session, user.id).save_version(strategy_id, spec)
    return StrategyVersionOut.from_model(version)


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionOut])
async def list_versions(
    strategy_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[StrategyVersionOut]:
    service = StrategyService(session, user.id)
    if await service.strategies.get(strategy_id) is None:
        raise NotFoundError()
    rows = await service.versions.for_strategy(strategy_id)
    return [StrategyVersionOut.from_model(row) for row in rows]


@router.get("/{strategy_id}/versions/{version}", response_model=StrategyVersionOut)
async def get_version(
    strategy_id: uuid.UUID, version: int, session: SessionDep, user: CurrentUser
) -> StrategyVersionOut:
    row = await StrategyService(session, user.id).versions.by_version(strategy_id, version)
    if row is None:
        raise NotFoundError()
    return StrategyVersionOut.from_model(row)
