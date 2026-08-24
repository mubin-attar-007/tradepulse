"""Password hashing (argon2id), session/CSRF cookies, and security headers.

Cookie naming follows the ``__Host-`` prefix in production (requires Secure +
Path=/ + no Domain); locally it falls back to a plain name since browsers
reject ``__Host-`` without HTTPS.

CSRF uses the double-submit pattern: a random token is written to a
JS-readable cookie and must be echoed back in the ``X-CSRF-Token`` header. The
*enforcement* of that contract lives in :func:`enforce_csrf`, which is called
from ``get_current_user`` — see the note there for why that is the single
choke point rather than a per-route dependency.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, PermissionDeniedError

_ph = PasswordHasher()

SESSION_COOKIE_SECURE = "__Host-session"
SESSION_COOKIE_PLAIN = "session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def constant_time_compare(presented: str, expected: str) -> bool:
    """Compare two secrets in constant time, safely for arbitrary attacker input.

    ``secrets.compare_digest`` raises ``TypeError`` on a ``str`` containing
    non-ASCII characters, so passing an attacker-controlled string straight in
    turns a rejection into a 500 — and a 500-vs-404 difference is itself an
    oracle telling the attacker the secret is configured. Comparing the UTF-8
    *bytes* accepts any input and still rejects it in constant time.
    """
    if not presented or not expected:
        return False
    return secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def bearer_token(request: Request) -> str:
    """``Authorization: Bearer <token>`` value, or "" when absent/another scheme."""
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return ""


def hash_password(raw: str) -> str:
    return _ph.hash(raw)


def verify_password(hashed: str, raw: str) -> bool:
    try:
        return _ph.verify(hashed, raw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def session_cookie_name() -> str:
    return SESSION_COOKIE_SECURE if get_settings().cookie_secure else SESSION_COOKIE_PLAIN


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=s.session_ttl_seconds,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
        # __Host- forbids a Domain attribute; only set Domain on the plain cookie.
        domain=None if s.cookie_secure else (s.cookie_domain or None),
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the session cookie with the SAME attributes it was set with.

    ``delete_cookie`` defaults to ``secure=False``, and a browser rejects any
    ``Set-Cookie`` for a ``__Host-``-prefixed name that lacks Secure + Path=/ —
    so the plain deletion is silently ignored in production and the user stays
    "logged in" with a cookie whose server-side session is already revoked.
    """
    s = get_settings()
    response.delete_cookie(
        key=session_cookie_name(),
        path="/",
        domain=None if s.cookie_secure else (s.cookie_domain or None),
        secure=s.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    clear_csrf_cookie(response)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        max_age=s.session_ttl_seconds,
        httponly=False,  # readable by the SPA to echo back in the header (double-submit)
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=CSRF_COOKIE, path="/", secure=s.cookie_secure, httponly=False, samesite="lax"
    )


def enforce_csrf(request: Request) -> None:
    """Fail-closed double-submit check for any unsafe, cookie-authenticated request.

    Called from ``get_current_user``, so it covers every endpoint that has
    ambient cookie authority — which is exactly the CSRF threat surface — and a
    new endpoint cannot forget to opt in. Requests with no session (login,
    register, password reset, the public/ops routers) never reach here and need
    no exemption list; safe methods return immediately.
    """
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not constant_time_compare(header, cookie):
        raise PermissionDeniedError("CSRF token missing or invalid.")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if get_settings().is_production:
            headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


class MetricsGuardMiddleware(BaseHTTPMiddleware):
    """Protect the Prometheus ``/metrics`` endpoint with a bearer token.

    Returns 404 (not 401, to avoid advertising the endpoint) when no METRICS_TOKEN is
    configured or the presented token is wrong. The scraper sends
    ``Authorization: Bearer <token>`` (or ``?token=``).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/metrics":
            token = get_settings().metrics_token
            presented = bearer_token(request) or request.query_params.get("token", "")
            if not constant_time_compare(presented, token):
                return Response(status_code=404)
        return await call_next(request)


TOO_LARGE_DETAIL = "Request body exceeds the maximum allowed size."


def _too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        media_type=PROBLEM_JSON,
        content={
            "type": "about:blank#payload_too_large",
            "title": "Payload Too Large",
            "status": 413,
            "detail": TOO_LARGE_DETAIL,
        },
    )


class BodySizeLimitMiddleware:
    """Reject over-large request bodies with 413 — whether or not a length is declared.

    Content-Length is the one thing an attacker is not obliged to send: a
    ``Transfer-Encoding: chunked`` request carries no length at all, so a
    header-only check waves through precisely the case it exists to stop and the
    body streams into memory anyway. This is raw ASGI rather than
    ``BaseHTTPMiddleware`` because bounding an undeclared body means owning the
    receive channel, which ``BaseHTTPMiddleware`` does not expose.

    Two paths, deliberately:

    * A declared length is checked against the limit and the body is then streamed
      through untouched — the overwhelming majority of traffic is unaffected.
    * An unsafe request with NO usable declared length is read here, capped, and
      replayed to the application. Buffering is the point: the limit promises a
      bound on how much of a request we will hold, and the only way to keep that
      promise for an undeclared body is to stop reading at the bound. Rejecting
      from inside the receive channel instead does not work — the exception
      surfaces inside a ``BaseHTTPMiddleware`` task group and reaches the app as
      an ExceptionGroup, which FastAPI reports as a 400 body-parse error.

    Safe methods with no declared length (ordinary GETs) are left completely alone.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_request_bytes
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit():
            if int(declared) > limit:
                await _too_large_response()(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        if scope.get("method", "GET") in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        pending: Message | None = None
        while True:
            message = await receive()
            if message["type"] != "http.request":
                pending = message  # a disconnect: hand it to the app unchanged
                break
            body += message.get("body", b"")
            if len(body) > limit:
                await _too_large_response()(scope, receive, send)
                return
            if not message.get("more_body", False):
                pending = {"type": "http.request", "body": bytes(body), "more_body": False}
                break

        async def replay() -> Message:
            nonlocal pending
            if pending is not None:
                message, pending = pending, None
                return message
            # Everything buffered has been handed over; fall through to the real
            # channel so disconnect detection behaves exactly as it did before.
            return await receive()

        await self.app(scope, replay, send)
