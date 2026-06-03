"""Auth flow: register -> me -> logout, plus negative cases."""

from __future__ import annotations

from httpx import AsyncClient

_PW = "password123"


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
