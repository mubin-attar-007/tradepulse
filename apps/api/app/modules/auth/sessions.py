"""Opaque, server-side sessions stored in Redis (revocable on logout).

The cookie carries only a random token; all state lives in Redis under a TTL,
so logout / forced revocation is a single key delete.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import get_settings

SESSION_PREFIX = "session:"


async def create_session(redis: Redis, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": str(user_id), "created_at": datetime.now(UTC).isoformat()})
    await redis.set(SESSION_PREFIX + token, payload, ex=get_settings().session_ttl_seconds)
    return token


async def get_session_user_id(redis: Redis, token: str) -> uuid.UUID | None:
    raw = await redis.get(SESSION_PREFIX + token)
    if not raw:
        return None
    try:
        return uuid.UUID(json.loads(raw)["user_id"])
    except (ValueError, KeyError, TypeError):
        return None


async def revoke_session(redis: Redis, token: str) -> None:
    await redis.delete(SESSION_PREFIX + token)
