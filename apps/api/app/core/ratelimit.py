"""Redis-backed fixed-window rate limiting (replaces the legacy blocking sleeps).

A global per-IP middleware applies the default budget; tighter per-endpoint
limits (e.g. login) use :func:`enforce_rate_limit` directly.
"""

from __future__ import annotations

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, RateLimitedError
from app.core.redis import get_redis_client

_EXEMPT_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json", "/redoc")


async def enforce_rate_limit(redis: Redis, identifier: str, limit: int, window: int = 60) -> None:
    """Fixed-window counter: raise :class:`RateLimitedError` past ``limit``/``window``."""
    key = f"rl:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        raise RateLimitedError(f"Rate limit exceeded ({limit} per {window}s).")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if any(request.url.path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        identifier = f"ip:{client_ip}:{request.url.path}"
        try:
            await enforce_rate_limit(
                get_redis_client(), identifier, get_settings().rate_limit_per_minute
            )
        except RateLimitedError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "type": "about:blank#rate_limited",
                    "title": exc.title,
                    "status": exc.status_code,
                    "detail": exc.detail,
                },
                media_type=PROBLEM_JSON,
            )
        return await call_next(request)
