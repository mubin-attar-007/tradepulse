"""Auth dependencies: current user, CSRF enforcement, and the ``get_owned`` factory.

These live in the auth module (not the kernel) so ``app.core`` stays free of
any knowledge of the user model.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.core.context import user_id_var
from app.core.db import OwnedEntity
from app.core.deps import RedisDep, SessionDep
from app.core.errors import AuthenticationError, NotFoundError
from app.core.repository import OwnedRepository
from app.core.security import enforce_csrf, session_cookie_name
from app.modules.auth.models import User
from app.modules.auth.sessions import get_session_user_id


async def get_current_user(request: Request, session: SessionDep, redis: RedisDep) -> User:
    """Resolve the session cookie to a user, and enforce CSRF on the way through.

    CSRF is checked HERE rather than per-route because this dependency is the one
    thing every cookie-authenticated endpoint already has in common (directly, or
    via ``get_owned``). The previous per-route ``Depends(csrf_protect)`` was wired
    to three of ~30 unsafe endpoints, so the mechanism read as enforced while
    ``POST /strategies`` accepted a bare session cookie. Anchoring it to the
    dependency makes it structurally impossible for a new authenticated route to
    opt out, and the check runs before the session lookup and the user query, so a
    forged request is rejected without a Redis read or a SELECT.

    Endpoints that legitimately have no session — login, register, password reset,
    /health, /ready, /metrics, /internal/*, the public router and the WebSocket
    handshake — do not depend on this, so they need no exemption list.
    """
    token = request.cookies.get(session_cookie_name())
    if not token:
        # No ambient authority to abuse yet: a missing session is 401, not a CSRF
        # failure. (Keeps unauthenticated POSTs answering 401 as they always have.)
        raise AuthenticationError()
    enforce_csrf(request)
    user_id = await get_session_user_id(redis, token)
    if user_id is None:
        raise AuthenticationError()
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError()
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


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
