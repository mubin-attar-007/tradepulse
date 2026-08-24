"""Auth flow: register -> me -> logout, plus negative cases and session lifecycle."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.redis import get_redis_client
from app.core.security import session_cookie_name
from app.modules.auth.reset import (
    RESET_PREFIX,
    RESET_TTL_SECONDS,
    consume_reset_token,
    create_reset_token,
)
from app.modules.auth.sessions import create_session, get_session_user_id

_PW = "password123"
_NEW_PW = "brand-new-password"


async def test_register_login_me_logout(client: AsyncClient) -> None:
    assert (await client.get("/auth/csrf")).status_code == 200

    resp = await client.post(
        "/auth/register",
        json={"email": "ada@example.com", "password": _PW, "display_name": "Ada"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "ada@example.com"

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"

    csrf = client.cookies.get("csrf_token")
    assert csrf
    logout = await client.post("/auth/logout", headers={"x-csrf-token": csrf})
    assert logout.status_code == 200

    # Session revoked server-side -> /me now unauthorized.
    assert (await client.get("/auth/me")).status_code == 401


async def test_me_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_success(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "grace@example.com", "password": _PW})
    resp = await client.post("/auth/login", json={"email": "grace@example.com", "password": _PW})
    assert resp.status_code == 200
    assert resp.json()["email"] == "grace@example.com"


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "alan@example.com", "password": _PW})
    resp = await client.post(
        "/auth/login", json={"email": "alan@example.com", "password": "not-the-password"}
    )
    assert resp.status_code == 401


async def test_duplicate_registration_conflicts(client: AsyncClient) -> None:
    body = {"email": "dup@example.com", "password": _PW}
    assert (await client.post("/auth/register", json=body)).status_code == 201
    assert (await client.post("/auth/register", json=body)).status_code == 409


async def test_logout_requires_csrf(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "linus@example.com", "password": _PW})
    # No CSRF header -> rejected even though the session is valid.
    assert (await client.post("/auth/logout")).status_code == 403


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post("/auth/register", json={"email": "x@example.com", "password": "short"})
    assert resp.status_code == 422


# --------------------------------------------------------------- session lifecycle


async def _register(client: AsyncClient, email: str) -> tuple[uuid.UUID, str, str]:
    """Register and return (user_id, csrf token, the session token now in the jar)."""
    resp = await client.post("/auth/register", json={"email": email, "password": _PW})
    assert resp.status_code == 201, resp.text
    csrf = client.cookies.get("csrf_token")
    session_token = client.cookies.get(session_cookie_name())
    assert csrf and session_token
    return uuid.UUID(resp.json()["id"]), csrf, session_token


async def test_change_password_revokes_other_sessions_and_rotates_the_current_one(
    client: AsyncClient,
) -> None:
    """A password change has to invalidate everything minted with the old password.

    Otherwise a stolen cookie outlives the change by the full 14-day session TTL —
    the exact outcome the user changed their password to prevent.
    """
    redis = get_redis_client()
    user_id, csrf, old_session = await _register(client, "rotate@example.com")
    phone = await create_session(redis, user_id)  # a second device, still signed in

    resp = await client.post(
        "/auth/change-password",
        json={"current_password": _PW, "new_password": _NEW_PW},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200, resp.text

    assert await get_session_user_id(redis, phone) is None  # other device signed out
    assert await get_session_user_id(redis, old_session) is None  # this one rotated
    assert client.cookies.get(session_cookie_name()) != old_session
    assert (await client.get("/auth/me")).status_code == 200  # ...but still signed in here

    assert (
        await client.post("/auth/login", json={"email": "rotate@example.com", "password": _NEW_PW})
    ).status_code == 200


async def test_password_reset_confirm_is_single_use_and_revokes_sessions(
    client: AsyncClient,
) -> None:
    redis = get_redis_client()
    user_id, _csrf, _session = await _register(client, "reset@example.com")
    token = await create_reset_token(redis, user_id)

    resp = await client.post(
        "/auth/password-reset-confirm", json={"token": token, "new_password": _NEW_PW}
    )
    assert resp.status_code == 200, resp.text

    # Whoever else held a session for this account is now out, including this browser.
    assert (await client.get("/auth/me")).status_code == 401
    # Replaying the link fails: consumption is atomic, not "delete afterwards".
    replay = await client.post(
        "/auth/password-reset-confirm", json={"token": token, "new_password": "another-password"}
    )
    assert replay.status_code == 401

    assert (
        await client.post("/auth/login", json={"email": "reset@example.com", "password": _NEW_PW})
    ).status_code == 200


async def test_reset_token_is_stored_hashed_with_a_ttl() -> None:
    """Redis holds a digest, not a usable link: a dump or a KEYS listing is inert."""
    redis = get_redis_client()
    user_id = uuid.uuid4()
    token = await create_reset_token(redis, user_id)

    assert await redis.get(RESET_PREFIX + token) is None  # not keyed by the raw token
    keys = await redis.keys(RESET_PREFIX + "*")
    assert len(keys) == 1
    assert token not in keys[0]
    ttl = await redis.ttl(keys[0])
    assert 0 < ttl <= RESET_TTL_SECONDS


async def test_issuing_a_reset_token_supersedes_the_previous_one() -> None:
    redis = get_redis_client()
    user_id = uuid.uuid4()
    first = await create_reset_token(redis, user_id)
    second = await create_reset_token(redis, user_id)

    assert await consume_reset_token(redis, first) is None
    assert await consume_reset_token(redis, second) == user_id


async def test_delete_account_revokes_every_session(client: AsyncClient) -> None:
    redis = get_redis_client()
    user_id, csrf, _session = await _register(client, "gone@example.com")
    phone = await create_session(redis, user_id)

    resp = await client.post("/auth/delete", json={"password": _PW}, headers={"x-csrf-token": csrf})
    assert resp.status_code == 200, resp.text

    assert await get_session_user_id(redis, phone) is None
    assert (await client.get("/auth/me")).status_code == 401


async def test_password_reset_request_is_generic_for_an_unknown_address(
    client: AsyncClient,
) -> None:
    resp = await client.post("/auth/password-reset", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
