"""Single-use, expiring password-reset tokens in Redis (mirrors the opaque-session design)."""

from __future__ import annotations

import secrets
import uuid

from redis.asyncio import Redis

RESET_PREFIX = "pwreset:"
RESET_TTL_SECONDS = 1800  # 30 minutes


async def create_reset_token(redis: Redis, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    await redis.set(RESET_PREFIX + token, str(user_id), ex=RESET_TTL_SECONDS)
    return token


async def consume_reset_token(redis: Redis, token: str) -> uuid.UUID | None:
    key = RESET_PREFIX + token
    raw = await redis.get(key)
    if not raw:
        return None
    await redis.delete(key)  # single-use
    try:
        return uuid.UUID(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, TypeError):
        return None
