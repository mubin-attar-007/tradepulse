"""Realtime fan-out: publish to Redis (worker) → RealtimeHub subscriber (web) → WS.

The hub keeps ONE Redis pub/sub subscription per channel (ref-counted) and
fans each message out to the connected WebSocket clients' queues. Pub/sub is
lossy by design; clients reconcile via the REST history endpoints on reconnect.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from decimal import Decimal

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.modules.market_data.repository import BarPoint

logger = get_logger("realtime")

_PRICE_TTL = 120  # seconds
TICKET_TTL = 30  # seconds — short-lived, one-time WS auth ticket


def _ticket_key(ticket: str) -> str:
    return f"wsticket:{ticket}"


async def issue_ws_ticket(redis: Redis, user_id: uuid.UUID) -> str:
    """Mint a short-lived one-time ticket so the browser can authenticate a
    cross-origin WebSocket without relying on cookies on the WS handshake."""
    ticket = secrets.token_urlsafe(32)
    await redis.set(_ticket_key(ticket), str(user_id), ex=TICKET_TTL)
    return ticket


async def redeem_ws_ticket(redis: Redis, ticket: str) -> uuid.UUID | None:
    raw = await redis.get(_ticket_key(ticket))
    if raw is None:
        return None
    await redis.delete(_ticket_key(ticket))  # one-time use
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def bars_channel(instrument_id: uuid.UUID) -> str:
    return f"bars:{instrument_id}"


def price_key(instrument_id: uuid.UUID) -> str:
    return f"price:{instrument_id}"


async def publish_bar(
    redis: Redis, instrument_id: uuid.UUID, bar: BarPoint, *, is_final: bool = True
) -> None:
    payload = json.dumps(
        {
            "instrument_id": str(instrument_id),
            "ts": bar.ts.isoformat(),
            "open": format(bar.open, "f"),
            "high": format(bar.high, "f"),
            "low": format(bar.low, "f"),
            "close": format(bar.close, "f"),
            "volume": format(bar.volume, "f"),
            "is_final": is_final,
        }
    )
    await redis.publish(bars_channel(instrument_id), payload)
    await redis.set(price_key(instrument_id), format(bar.close, "f"), ex=_PRICE_TTL)


async def get_latest_price(redis: Redis, instrument_id: uuid.UUID) -> Decimal | None:
    raw = await redis.get(price_key(instrument_id))
    return Decimal(raw) if raw is not None else None


class RealtimeHub:
    """Per-process fan-out from Redis channels to WebSocket client queues."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._queues: dict[str, set[asyncio.Queue[str]]] = {}
        self._readers: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            subscribers = self._queues.setdefault(channel, set())
            subscribers.add(queue)
            if channel not in self._readers:
                self._readers[channel] = asyncio.create_task(self._reader(channel))

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            subscribers = self._queues.get(channel)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._queues.pop(channel, None)
                task = self._readers.pop(channel, None)
                if task is not None:
                    task.cancel()

    async def _reader(self, channel: str) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message["data"]
                for queue in list(self._queues.get(channel, ())):
                    if queue.full():
                        continue  # drop for slow consumers; they reconcile via REST
                    queue.put_nowait(data)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        async with self._lock:
            for task in self._readers.values():
                task.cancel()
            self._readers.clear()
            self._queues.clear()


_hub: RealtimeHub | None = None


def get_hub() -> RealtimeHub:
    global _hub
    if _hub is None:
        _hub = RealtimeHub(get_redis_client())
    return _hub


async def close_hub() -> None:
    global _hub
    if _hub is not None:
        await _hub.close()
    _hub = None
