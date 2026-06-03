"""Async Redis client (cache, pub/sub, sessions, rate-limit, ARQ).

A single decode-responses client is shared per process. Phase 2 adds a raw
(bytes) client for binary pub/sub payloads; for now strings suffice.
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from app.core.config import get_settings

_redis: Redis | None = None


def get_redis_client() -> Redis:
    global _redis
    if _redis is None:
        _redis = redis_from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)
    return _redis


async def get_redis() -> Redis:
    """FastAPI dependency."""
    return get_redis_client()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None
