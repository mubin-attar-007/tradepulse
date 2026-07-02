"""Auth HTTP endpoints: csrf, register, login, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from starlette.requests import Request

from app.core.config import get_settings
from app.core.deps import RedisDep, SessionDep
from app.core.email import send_email
from app.core.errors import AuthenticationError
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
from app.modules.auth.reset import consume_reset_token, create_reset_token
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    UserOut,
)
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


@router.post("/change-password", dependencies=[Depends(csrf_protect)])
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    user: CurrentUser,
) -> dict[str, str]:
    await enforce_rate_limit(redis, f"pwchange:{user.id}", limit=10, window=60)
    await AuthService(session).change_password(
        user.id, payload.current_password, payload.new_password
    )
    await audit.record(
        session, action="user.change_password", actor_id=user.id, ip=_client_ip(request)
    )
    return {"status": "ok"}


@router.post("/delete", dependencies=[Depends(csrf_protect)])
async def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    user: CurrentUser,
) -> dict[str, str]:
    svc = AuthService(session)
    if not await svc.verify_current_password(user.id, payload.password):
        raise AuthenticationError("Password is incorrect.")
    await svc.deactivate(user.id)
    await audit.record(session, action="user.delete", actor_id=user.id, ip=_client_ip(request))
    token = request.cookies.get(session_cookie_name())
    if token:
        await revoke_session(redis, token)
    clear_session_cookie(response)
    return {"status": "ok"}


@router.post("/password-reset")
async def password_reset(
    payload: PasswordResetRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str]:
    """Start a reset. Always a generic 200 (no account enumeration); emails a link when real."""
    await enforce_rate_limit(redis, f"pwreset:{_client_ip(request)}", limit=5, window=300)
    user = await AuthService(session).get_by_email(payload.email)
    if user is not None and user.is_active:
        token = await create_reset_token(redis, user.id)
        reset_url = f"{get_settings().frontend_url.rstrip('/')}/reset-password?token={token}"
        await send_email(
            user.email,
            "Reset your TradePulse password",
            "Reset your TradePulse password with this link (expires in 30 minutes):\n\n"
            f"{reset_url}\n\nIf you didn't request this, you can safely ignore this email.",
        )
    return {"status": "ok"}


@router.post("/password-reset-confirm")
async def password_reset_confirm(
    payload: PasswordResetConfirm,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str]:
    user_id = await consume_reset_token(redis, payload.token)
    if user_id is None:
        raise AuthenticationError("This reset link is invalid or has expired.")
    await AuthService(session).set_password(user_id, payload.new_password)
    return {"status": "ok"}
