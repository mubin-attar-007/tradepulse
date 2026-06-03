"""Paper-trading endpoints (auth-gated, owner-scoped). PAPER only — no live
broker execution here (that is the gated Phase 8 seam)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.errors import NotFoundError
from app.modules.auth.deps import CurrentUser
from app.modules.trading import schemas
from app.modules.trading.service import PaperService

router = APIRouter(prefix="/paper", tags=["paper-trading"])


@router.post("/deploy", status_code=201, response_model=schemas.PaperSessionOut)
async def deploy(
    payload: schemas.DeployRequest, session: SessionDep, user: CurrentUser
) -> schemas.PaperSessionOut:
    service = PaperService(session, user.id)
    paper = await service.deploy(payload.strategy_id)
    await service.run_session(paper)  # populate the desk immediately
    return schemas.PaperSessionOut.model_validate(paper)


@router.get("/sessions", response_model=list[schemas.PaperSessionOut])
async def list_sessions(session: SessionDep, user: CurrentUser) -> list[schemas.PaperSessionOut]:
    rows = await PaperService(session, user.id).sessions.list_for_owner()
    return [schemas.PaperSessionOut.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=schemas.PaperSessionOut)
async def get_session(
    session_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> schemas.PaperSessionOut:
    paper = await PaperService(session, user.id).sessions.get(session_id)
    if paper is None:
        raise NotFoundError()
    return schemas.PaperSessionOut.model_validate(paper)


@router.post("/sessions/{session_id}/run", response_model=schemas.PaperSessionOut)
async def run_now(
    session_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> schemas.PaperSessionOut:
    service = PaperService(session, user.id)
    paper = await service.sessions.get(session_id)
    if paper is None:
        raise NotFoundError()
    await service.run_session(paper)
    return schemas.PaperSessionOut.model_validate(paper)


@router.post("/sessions/{session_id}/stop", response_model=schemas.PaperSessionOut)
async def stop(
    session_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> schemas.PaperSessionOut:
    paper = await PaperService(session, user.id).stop(session_id)
    return schemas.PaperSessionOut.model_validate(paper)
