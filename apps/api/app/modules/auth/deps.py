"""Auth dependencies: current user, CSRF protection, and the ``get_owned`` factory.

These live in the auth module (not the kernel) so ``app.core`` stays free of
any knowledge of the user model.
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.core.context import user_id_var
from app.core.db import OwnedEntity
from app.core.deps import RedisDep, SessionDep
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.repository import OwnedRepository
from app.core.security import CSRF_COOKIE, CSRF_HEADER, SAFE_METHODS, session_cookie_name
from app.modules.auth.models import User
from app.modules.auth.sessions import get_session_user_id


async def get_current_user(request: Request, session: SessionDep, redis: RedisDep) -> User:
    token = request.cookies.get(session_cookie_name())
    if not token:
        raise AuthenticationError()
    user_id = await get_session_user_id(redis, token)
    if user_id is None:
        raise AuthenticationError()
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError()
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def csrf_protect(request: Request) -> None:
    """Double-submit CSRF check for unsafe methods (defense-in-depth + SameSite)."""
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise PermissionDeniedError("CSRF token missing or invalid.")


def get_owned(
    repo_cls: type[OwnedRepository[OwnedEntity]],
) -> Callable[..., Awaitable[OwnedEntity]]:
    """Dependency factory: fetch an owner-scoped row by id or 404 (never 403,
    so non-ownership doesn't leak existence)."""

    async def _dep(id_: uuid.UUID, session: SessionDep, user: CurrentUser) -> OwnedEntity:
        obj = await repo_cls(session, user.id).get(id_)
        if obj is None:
            raise NotFoundError()
        return obj

    return _dep
