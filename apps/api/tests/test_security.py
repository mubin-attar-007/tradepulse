"""Application-security invariants that are easy to *look* enforced and not be.

Covers the three mechanisms whose failure modes are silent: CSRF double-submit
(previously wired to 3 of ~30 unsafe endpoints), the proxy-aware client IP that
the rate limiter buckets on, and session-cookie deletion (a ``__Host-`` cookie
survives a Set-Cookie that omits Secure).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.ratelimit import _parse_ip, account_bucket, client_ip
from app.core.redis import get_redis_client
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE_SECURE,
    clear_session_cookie,
    constant_time_compare,
)
from app.modules.auth.sessions import create_session, get_session_user_id, revoke_user_sessions

_PW = "password123"


def _request(
    *,
    method: str = "POST",
    peer: str | None = "198.51.100.4",
    headers: dict[str, str] | None = None,
) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/",
            "headers": raw,
            "query_string": b"",
            "client": (peer, 51234) if peer else None,
        }
    )


async def _register(client: AsyncClient, email: str) -> str:
    """Register (which mints session + CSRF cookies) and return the CSRF token."""
    resp = await client.post("/auth/register", json={"email": email, "password": _PW})
    assert resp.status_code == 201, resp.text
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf
    return csrf


# --------------------------------------------------------------------------- CSRF


async def test_unsafe_request_without_csrf_header_is_rejected(client: AsyncClient) -> None:
    await _register(client, "csrf-missing@example.com")
    resp = await client.post("/market/ws-ticket")
    assert resp.status_code == 403, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 403


async def test_unsafe_request_with_mismatched_csrf_header_is_rejected(client: AsyncClient) -> None:
    await _register(client, "csrf-wrong@example.com")
    resp = await client.post("/market/ws-ticket", headers={"x-csrf-token": "not-the-token"})
    assert resp.status_code == 403, resp.text


async def test_unsafe_request_with_matching_csrf_header_succeeds(client: AsyncClient) -> None:
    csrf = await _register(client, "csrf-ok@example.com")
    resp = await client.post("/market/ws-ticket", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket"]


async def test_safe_get_is_unaffected_by_csrf(client: AsyncClient) -> None:
    await _register(client, "csrf-get@example.com")
    assert (await client.get("/auth/me")).status_code == 200


async def test_mutating_trading_endpoint_requires_csrf(client: AsyncClient) -> None:
    """The endpoint class the old per-route wiring missed entirely.

    With the header the request reaches the handler and 404s on the unknown id —
    which is what proves the 403 came from CSRF and not from the route being absent.
    """
    csrf = await _register(client, "csrf-paper@example.com")
    unknown = uuid.uuid4()
    assert (await client.post(f"/paper/sessions/{unknown}/stop")).status_code == 403
    with_header = await client.post(
        f"/paper/sessions/{unknown}/stop", headers={"x-csrf-token": csrf}
    )
    assert with_header.status_code == 404, with_header.text


async def test_unauthenticated_unsafe_request_is_still_401(client: AsyncClient) -> None:
    """No session cookie means no ambient authority to forge with: 401, not 403."""
    assert (await client.post("/market/ws-ticket")).status_code == 401


# ------------------------------------------------------------- constant-time compare


def test_constant_time_compare_rejects_non_ascii_without_raising() -> None:
    # secrets.compare_digest on a non-ASCII *str* raises TypeError, which used to
    # turn a rejected token into a 500 — a 500-vs-404 oracle for "is this armed".
    assert constant_time_compare("ééé", "abc") is False


@pytest.mark.parametrize(
    ("presented", "expected", "match"),
    [("s3cret", "s3cret", True), ("s3cret", "s3crey", False), ("", "s3cret", False)],
)
def test_constant_time_compare(presented: str, expected: str, match: bool) -> None:
    assert constant_time_compare(presented, expected) is match


# ----------------------------------------------------------------- client IP / buckets


def _settings(**kwargs: object) -> Settings:
    # Explicit kwargs outrank env and .env in pydantic-settings, so these are hermetic.
    return Settings(**kwargs)  # type: ignore[arg-type]


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.ratelimit.get_settings", lambda: _settings())
    req = _request(headers={"x-forwarded-for": "1.2.3.4"})
    assert client_ip(req) == "198.51.100.4"  # the socket peer, not the claim


def test_client_ip_takes_the_hop_the_trusted_proxy_appended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.ratelimit.get_settings",
        lambda: _settings(trust_proxy_headers=True, trusted_proxy_hops=1),
    )
    # An attacker pre-seeds the header; our proxy APPENDS the address it heard from.
    req = _request(headers={"x-forwarded-for": "9.9.9.9, 203.0.113.7"})
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_counts_hops_from_the_right(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.ratelimit.get_settings",
        lambda: _settings(trust_proxy_headers=True, trusted_proxy_hops=2),
    )
    req = _request(headers={"x-forwarded-for": "9.9.9.9, 203.0.113.7, 10.0.0.2"})
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_peer_on_a_short_or_junk_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.ratelimit.get_settings",
        lambda: _settings(trust_proxy_headers=True, trusted_proxy_hops=2),
    )
    assert client_ip(_request(headers={"x-forwarded-for": "203.0.113.7"})) == "198.51.100.4"
    assert client_ip(_request(headers={"x-forwarded-for": "a, drop-table"})) == "198.51.100.4"
    assert client_ip(_request()) == "198.51.100.4"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 203.0.113.7:443 ", "203.0.113.7"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("not-an-ip", None),
        ("", None),
    ],
)
def test_parse_ip(raw: str, expected: str | None) -> None:
    assert _parse_ip(raw) == expected


def test_account_bucket_is_stable_normalized_and_opaque() -> None:
    assert account_bucket("login", " Ada@Example.com ") == account_bucket(
        "login", "ada@example.com"
    )
    assert account_bucket("login", "ada@example.com") != account_bucket("login", "bob@example.com")
    assert "ada@example.com" not in account_bucket("login", "ada@example.com")


# ------------------------------------------------------------------- cookie deletion


def test_session_cookie_deletion_carries_secure_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A browser ignores a Set-Cookie for a ``__Host-`` name without Secure + Path=/.

    Without these attributes logout revokes the server-side session but leaves the
    cookie in place, and the SPA's cookie-presence check keeps redirecting the user
    into an authenticated route that then 401s.
    """
    monkeypatch.setattr(
        "app.core.security.get_settings", lambda: _settings(cookie_secure=True, cookie_domain="")
    )
    response = Response()
    clear_session_cookie(response)
    headers = [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]
    session_header = next(h for h in headers if SESSION_COOKIE_SECURE in h)
    assert "Secure" in session_header
    assert "Path=/" in session_header
    assert "Domain=" not in session_header  # __Host- forbids Domain
    # The JS-readable CSRF cookie has to go too, or the SPA keeps echoing a dead token.
    assert any(CSRF_COOKIE in h for h in headers)


# ------------------------------------------------------------------ session revocation


async def test_revoke_user_sessions_kills_every_token_but_the_kept_one() -> None:
    redis = get_redis_client()
    user_id = uuid.uuid4()
    other_user = uuid.uuid4()
    keep = await create_session(redis, user_id)
    doomed = [await create_session(redis, user_id) for _ in range(3)]
    untouched = await create_session(redis, other_user)

    assert await revoke_user_sessions(redis, user_id, keep=keep) == 3

    assert await get_session_user_id(redis, keep) == user_id
    for token in doomed:
        assert await get_session_user_id(redis, token) is None
    assert await get_session_user_id(redis, untouched) == other_user
    # Revoking again is a no-op, not a double count (the index was pruned).
    assert await revoke_user_sessions(redis, user_id, keep=keep) == 0


# --------------------------------------------------------- credential rate limiting


@asynccontextmanager
async def _client_from(peer: str) -> AsyncIterator[AsyncClient]:
    """A client whose socket peer is ``peer``, so per-IP buckets can be told apart."""
    from app.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app, client=(peer, 51234))
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_login_budget_is_per_account_as_well_as_per_ip() -> None:
    """A guessing attack that rotates source addresses must still hit a wall.

    The per-IP budget alone is the wrong shape twice over: behind a proxy it is one
    bucket for the whole platform, and against a botnet it is no bucket at all for
    the account actually under attack.
    """
    async with _client_from("203.0.113.10") as first, _client_from("203.0.113.11") as second:
        assert (
            await first.post(
                "/auth/register", json={"email": "target@example.com", "password": _PW}
            )
        ).status_code == 201

        attempts = [*([first] * 5), *([second] * 6)]
        statuses = [
            (
                await attacker.post(
                    "/auth/login", json={"email": "target@example.com", "password": "guess"}
                )
            ).status_code
            for attacker in attempts
        ]

    # Ten wrong guesses land (well inside the 10/60 per-IP budget on either address);
    # the eleventh exhausts the account's own budget regardless of where it came from.
    assert statuses[:10] == [401] * 10, statuses
    assert statuses[10] == 429, statuses


# --------------------------------------------------------------------- body size


def _tiny_body_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings(max_request_bytes=1024))


async def test_declared_oversize_body_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_body_limit(monkeypatch)
    resp = await client.post("/auth/login", json={"email": "a@b.co", "password": "x" * 4096})
    assert resp.status_code == 413, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_undeclared_chunked_body_is_still_bounded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Content-Length is the one thing an attacker need not send.

    A chunked request declares no length, so a header-only limit skips the check
    entirely and the body streams into memory — the exact case the limit is for.
    """
    _tiny_body_limit(monkeypatch)

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(8):
            yield b"x" * 512

    resp = await client.post(
        "/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert "content-length" not in {k.lower() for k in resp.request.headers}
    assert resp.status_code == 413, resp.text


async def test_small_chunked_body_passes_through(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counter must be invisible to every request that is not oversized."""
    _tiny_body_limit(monkeypatch)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"email":"nobody@example.com","password":"password123"}'

    resp = await client.post(
        "/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert resp.status_code == 401, resp.text  # reached the handler; bad credentials
