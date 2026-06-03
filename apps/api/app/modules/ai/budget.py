"""Per-user + global daily AI token budgets (Redis), so a runaway loop or a bug
can't bankrupt the operator. Checked before a call, recorded after."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.errors import RateLimitedError

DAILY_USER_TOKENS = 200_000
DAILY_GLOBAL_TOKENS = 5_000_000
_TTL = 172_800  # 2 days


def _day() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _user_key(user_id: uuid.UUID) -> str:
    return f"aibudget:user:{user_id}:{_day()}"


def _global_key() -> str:
    return f"aibudget:global:{_day()}"


async def check(redis: Redis, user_id: uuid.UUID) -> None:
    if int(await redis.get(_user_key(user_id)) or 0) >= DAILY_USER_TOKENS:
        raise RateLimitedError("Daily AI budget reached. Try again tomorrow.")
    if int(await redis.get(_global_key()) or 0) >= DAILY_GLOBAL_TOKENS:
        raise RateLimitedError("AI is temporarily at capacity. Try again later.")


async def record(redis: Redis, user_id: uuid.UUID, tokens: int) -> None:
    if tokens <= 0:
        return
    for key in (_user_key(user_id), _global_key()):
        await redis.incrby(key, tokens)
        await redis.expire(key, _TTL)
