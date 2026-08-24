"""Opaque, server-side sessions stored in Redis (revocable on logout).

The cookie carries only a random token; all state lives in Redis under a TTL,
so logout / forced revocation is a single key delete.

Each token is also recorded in a per-user index set, which is what makes
*mass* revocation possible: after a password change or a completed reset we
have to invalidate every OTHER session, and with a bare ``session:<token>``
keyspace there is no way to find them without scanning all of Redis.
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis

from app.core.config import get_settings

SESSION_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"


def _index_key(user_id: uuid.UUID) -> str:
    return f"{USER_SESSIONS_PREFIX}{user_id}"


def _user_id_from(raw: str | bytes | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(json.loads(raw)["user_id"])
    except (ValueError, KeyError, TypeError):
        return None


async def create_session(redis: Redis, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    ttl = get_settings().session_ttl_seconds
    payload = json.dumps({"user_id": str(user_id), "created_at": datetime.now(UTC).isoformat()})
    # NOTE: this is index-driven, so it can only revoke what the index knows about.
    # A session minted before the index existed (or after an eviction, or a partial
    # flush) is invisible here — which is why callers ALSO revoke the presenting
    # token explicitly rather than relying on this alone.
    index = _index_key(user_id)
    pipe = redis.pipeline()
    pipe.set(SESSION_PREFIX + token, payload, ex=ttl)
    pipe.sadd(index, token)
    # Refresh the index TTL alongside the newest member so the set cannot outlive
    # the last session by more than one TTL. Members whose session key has already
    # expired are harmless: revoking them deletes a key that is already gone.
    pipe.expire(index, ttl)
    await pipe.execute()
    return token


async def get_session_user_id(redis: Redis, token: str) -> uuid.UUID | None:
    return _user_id_from(await redis.get(SESSION_PREFIX + token))


async def revoke_session(redis: Redis, token: str) -> None:
    key = SESSION_PREFIX + token
    user_id = _user_id_from(await redis.get(key))
    pipe = redis.pipeline()
    pipe.delete(key)
    if user_id is not None:
        pipe.srem(_index_key(user_id), token)
    await pipe.execute()


async def revoke_user_sessions(redis: Redis, user_id: uuid.UUID, *, keep: str | None = None) -> int:
    """Revoke every session for ``user_id`` (optionally sparing ``keep``).

    Called when the credential that minted those sessions stops being the one the
    user knows — a password change or a completed reset. Without this a stolen
    cookie survives the reset for the full 14-day session TTL, which is precisely
    what the user was resetting to prevent. Returns how many were revoked.
    """
    index = _index_key(user_id)
    # redis-py types every command as `Awaitable[T] | T` to share one class between
    # the sync and async clients; on the async client it is always the awaitable.
    tokens: set[str] = await cast("Awaitable[set[str]]", redis.smembers(index))
    victims = [t for t in tokens if t != keep]
    if not victims:
        return 0
    pipe = redis.pipeline()
    for token in victims:
        pipe.delete(SESSION_PREFIX + token)
    pipe.srem(index, *victims)
    await pipe.execute()
    return len(victims)
