"""Redis-backed fixed-window rate limiting (replaces the legacy blocking sleeps).

A global per-IP middleware applies the default budget; tighter per-endpoint
limits (e.g. login) use :func:`enforce_rate_limit` directly.

:func:`client_ip` is the single source of truth for "who is this request from",
shared by the middleware and by the auth router's per-IP budgets — two different
answers to that question is how a limit ends up enforced against the proxy.
"""

from __future__ import annotations

import hashlib
import ipaddress

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, RateLimitedError
from app.core.redis import get_redis_client

# /metrics is token-gated and scraped on a fixed interval; throttling it only ever
# breaks monitoring, and a throttled scrape looks identical to a dead process.
_EXEMPT_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json", "/redoc", "/metrics")

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


def _parse_ip(raw: str) -> str | None:
    """Normalize one forwarded hop to a bare IP, or ``None`` if it is not one.

    Rejecting non-IPs matters for more than tidiness: the result becomes part of a
    Redis key, so an unvalidated header value is unbounded attacker-chosen key
    cardinality in our own datastore."""
    candidate = raw.strip()
    if candidate.startswith("[") and "]" in candidate:  # [2001:db8::1]:443
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # 203.0.113.7:443 (IPv6 has more colons)
        candidate = candidate.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """The address to bill this request to, given how many proxies we actually have.

    ``X-Forwarded-For`` is a list any client can pre-seed, and each proxy only
    APPENDS the peer it heard from. So the leftmost entry is whatever the attacker
    wrote — trusting it hands every request a fresh, private rate-limit bucket and
    turns the limiter off. The value our own outermost proxy appended is the Nth
    from the right, where N is ``trusted_proxy_hops``.

    With ``trust_proxy_headers`` off (the default, and correct locally) the socket
    peer *is* the client, so we use it and ignore the header entirely. Behind a
    proxy without the setting on, everyone shares the proxy's bucket — noisy, but
    fail-closed; the reverse mistake is silent and total.
    """
    peer = request.client.host if request.client else "unknown"
    settings = get_settings()
    if not settings.trust_proxy_headers:
        return peer
    hops = [h for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    index = len(hops) - max(1, settings.trusted_proxy_hops)
    if index < 0:
        # Fewer hops than configured: the chain was not produced by the proxy layer
        # we think we have. Fall back to the peer rather than believe the header.
        return peer
    return _parse_ip(hops[index]) or peer


async def clear_rate_limit(redis: Redis, identifier: str) -> None:
    """Reset a budget after the action it guards succeeded.

    Only meaningful for budgets that exist to slow down GUESSING. A counter that
    survives a correct answer stops being a brute-force control and becomes a
    lockout an attacker can drive on the victim's behalf.
    """
    await redis.delete(f"rl:{identifier}")


def account_bucket(prefix: str, account: str) -> str:
    """Rate-limit identifier keyed on an account, hashed so no email reaches Redis.

    Per-IP budgets alone are the wrong shape for credential endpoints: behind a
    proxy one bucket covers everybody (so any visitor can lock out the platform),
    and with a botnet no bucket covers the account actually under attack."""
    digest = hashlib.sha256(account.strip().lower().encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:acct:{digest}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)
        ip = client_ip(request)
        settings = get_settings()
        # Coarse route-group key (no full path): a per-path key would let each URL —
        # e.g. every ticker — spend a fresh budget. Public bars gets its own tighter
        # bucket; everything else shares the default per-IP budget.
        if path.startswith(_PUBLIC_BARS_PREFIX) and path.endswith("/bars"):
            identifier = f"ip:{ip}:public_bars"
            limit = _PUBLIC_BARS_LIMIT
        else:
            identifier = f"ip:{ip}"
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
