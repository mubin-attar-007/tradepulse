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

# Tighter dedicated budget for the anonymous, expensive public bars endpoint so a
# single client can't hammer it (it aggregates OHLCV per request). Coarse per-IP,
# NOT per-ticker — keying on the exact path would hand each ticker a fresh budget.
_PUBLIC_BARS_PREFIX = "/public/markets/"
_PUBLIC_BARS_LIMIT = 30


async def enforce_rate_limit(redis: Redis, identifier: str, limit: int, window: int = 60) -> None:
    """Fixed-window counter: raise :class:`RateLimitedError` past ``limit``/``window``."""
    key = f"rl:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        raise RateLimitedError(f"Rate limit exceeded ({limit} per {window}s).")


def _client_ip(request: Request) -> str:
    """Real client IP behind a proxy (HF Spaces / Render terminate TLS upstream).

    ``request.client.host`` is the PROXY's IP there, so every user shares one bucket.
    Trust the leftmost hop of ``X-Forwarded-For`` (the original client) instead."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)
        client_ip = _client_ip(request)
        settings = get_settings()
        # Coarse route-group key (no full path): a per-path key would let each URL —
        # e.g. every ticker — spend a fresh budget. Public bars gets its own tighter
        # bucket; everything else shares the default per-IP budget.
        if path.startswith(_PUBLIC_BARS_PREFIX) and path.endswith("/bars"):
            identifier = f"ip:{client_ip}:public_bars"
            limit = _PUBLIC_BARS_LIMIT
        else:
            identifier = f"ip:{client_ip}"
            limit = settings.rate_limit_per_minute
        try:
            await enforce_rate_limit(get_redis_client(), identifier, limit)
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
