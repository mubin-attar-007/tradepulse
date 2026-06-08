"""Password hashing (argon2id), session/CSRF cookies, and security headers.

Cookie naming follows the ``__Host-`` prefix in production (requires Secure +
Path=/ + no Domain); locally it falls back to a plain name since browsers
reject ``__Host-`` without HTTPS.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

_ph = PasswordHasher()

SESSION_COOKIE_SECURE = "__Host-session"
SESSION_COOKIE_PLAIN = "session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


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
    response.delete_cookie(key=session_cookie_name(), path="/")


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
            auth = request.headers.get("authorization", "")
            presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not presented:
                presented = request.query_params.get("token", "")
            if not token or not secrets.compare_digest(presented, token):
                return Response(status_code=404)
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds the configured limit (413)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > get_settings().max_request_bytes
            except ValueError:
                too_large = False
            if too_large:
                return JSONResponse(
                    status_code=413,
                    media_type="application/problem+json",
                    content={
                        "type": "about:blank#payload_too_large",
                        "title": "Payload Too Large",
                        "status": 413,
                        "detail": "Request body exceeds the maximum allowed size.",
                    },
                )
        return await call_next(request)
