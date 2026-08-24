"""Single-use, expiring password-reset tokens in Redis (mirrors the opaque-session design).

Three properties this file is responsible for, in order of how badly each one
bites when it is missing:

* **Not recoverable from storage.** Only the SHA-256 of the token is used as the
  key, so a Redis dump, a ``KEYS`` listing or a slowlog entry yields digests, not
  usable reset links. The token itself exists only in the email.
* **Single-use, atomically.** ``GETDEL`` reads and deletes in one round trip, so
  two requests racing with the same token cannot both win — a get-then-delete
  pair can.
* **One live token per user.** Issuing a new link invalidates the previous one,
  so an older email (forwarded, sitting in a shared inbox, or requested by an
  attacker fishing for one) stops working the moment the real user asks again.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from redis.asyncio import Redis

RESET_PREFIX = "pwreset:tok:"
RESET_USER_PREFIX = "pwreset:user:"
RESET_TTL_SECONDS = 1800  # 30 minutes


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_key(user_id: uuid.UUID) -> str:
    return f"{RESET_USER_PREFIX}{user_id}"


async def create_reset_token(redis: Redis, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    digest = _digest(token)
    user_key = _user_key(user_id)
    previous = await redis.get(user_key)
    pipe = redis.pipeline()
    if previous:
        pipe.delete(RESET_PREFIX + previous)
    pipe.set(RESET_PREFIX + digest, str(user_id), ex=RESET_TTL_SECONDS)
    # The pointer holds the digest too, so it is as useless as the key it points at.
    pipe.set(user_key, digest, ex=RESET_TTL_SECONDS)
    await pipe.execute()
    return token


async def consume_reset_token(redis: Redis, token: str) -> uuid.UUID | None:
    raw = await redis.getdel(RESET_PREFIX + _digest(token))  # atomic => single-use under a race
    if not raw:
        return None
    try:
        user_id = uuid.UUID(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, TypeError):
        return None
    await redis.delete(_user_key(user_id))
    return user_id
