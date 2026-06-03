"""Minimal domain-event seam: an in-process bus + Redis pub/sub bridge.

This is the thin ``EventPublisher`` interface the architecture calls for. The
transactional outbox is intentionally deferred until real-money async broker
fills require at-least-once cross-process delivery (see plan reconciliation).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger("events")
EVENTS_CHANNEL = "events"

Handler = Callable[["DomainEvent"], Awaitable[None]]


@dataclass(slots=True)
class DomainEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class InProcessEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, name: str, handler: Handler) -> None:
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.name, []):
            try:
                await handler(event)
            except Exception:
                logger.exception("event_handler_failed", event=event.name)
        # Lossy fan-out for UI realtime (consumers reconcile via REST snapshot).
        try:
            await get_redis_client().publish(
                EVENTS_CHANNEL,
                json.dumps(
                    {
                        "name": event.name,
                        "payload": event.payload,
                        "occurred_at": event.occurred_at.isoformat(),
                    }
                ),
            )
        except Exception:
            logger.warning("event_redis_publish_failed", event=event.name)


_bus = InProcessEventBus()


def get_event_bus() -> InProcessEventBus:
    return _bus
