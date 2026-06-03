"""Auth HTTP endpoints: csrf, register, login, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from starlette.requests import Request

from app.core.deps import RedisDep, SessionDep
from app.core.ratelimit import enforce_rate_limit
from app.core.security import (
    clear_session_cookie,
    generate_csrf_token,
    session_cookie_name,
    set_csrf_cookie,
    set_session_cookie,
)
from app.modules.audit import service as audit
from app.modules.auth.deps import CurrentUser, csrf_protect
from app.modules.auth.schemas import LoginRequest, RegisterRequest, UserOut
from app.modules.auth.service import AuthService
from app.modules.auth.sessions import create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/csrf", summary="Issue a CSRF token (sets cookie + returns token)")
async def issue_csrf(response: Response) -> dict[str, str]:
    token = generate_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


@router.post("/register", status_code=201, response_model=UserOut)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
) -> UserOut:
    user = await AuthService(session).register(
        payload.email, payload.password, payload.display_name
    )
    await audit.record(
        session,
        action="user.register",
        actor_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip=_client_ip(request),
    )
    set_session_cookie(response, await create_session(redis, user.id))
    set_csrf_cookie(response, generate_csrf_token())
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
) -> UserOut:
    await enforce_rate_limit(redis, f"login:{_client_ip(request)}", limit=10, window=60)
    user = await AuthService(session).authenticate(payload.email, payload.password)
    await audit.record(
        session,
        action="user.login",
        actor_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip=_client_ip(request),
    )
    set_session_cookie(response, await create_session(redis, user.id))
    set_csrf_cookie(response, generate_csrf_token())
    return UserOut.model_validate(user)


@router.post("/logout", dependencies=[Depends(csrf_protect)])
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    user: CurrentUser,
) -> dict[str, str]:
    token = request.cookies.get(session_cookie_name())
    if token:
        await revoke_session(redis, token)
    await audit.record(session, action="user.logout", actor_id=user.id, ip=_client_ip(request))
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
