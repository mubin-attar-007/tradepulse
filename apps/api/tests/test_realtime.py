"""Realtime publish + RealtimeHub fan-out + WS ticket auth."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.redis import get_redis_client
from app.modules.market_data import realtime
from app.modules.market_data.repository import BarPoint


def _barpoint() -> BarPoint:
    return BarPoint(
        ts=datetime(2024, 1, 2, 15, 0, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("2"),
    )


async def test_publish_sets_latest_price() -> None:
    redis = get_redis_client()
    iid = uuid.uuid4()
    await realtime.publish_bar(redis, iid, _barpoint())
    assert await realtime.get_latest_price(redis, iid) == Decimal("100.5")


async def test_ws_ticket_is_one_time() -> None:
    redis = get_redis_client()
    uid = uuid.uuid4()
    ticket = await realtime.issue_ws_ticket(redis, uid)
    assert await realtime.redeem_ws_ticket(redis, ticket) == uid
    assert await realtime.redeem_ws_ticket(redis, ticket) is None  # consumed


async def test_hub_fans_out_messages() -> None:
    redis = get_redis_client()
    hub = realtime.RealtimeHub(redis)
    iid = uuid.uuid4()
    channel = realtime.bars_channel(iid)
    queue: asyncio.Queue[str] = asyncio.Queue()
    await hub.subscribe(channel, queue)
    try:
        await asyncio.sleep(0.3)  # let the reader's Redis subscribe take effect
        await realtime.publish_bar(redis, iid, _barpoint())
        message = await asyncio.wait_for(queue.get(), timeout=3)
        assert json.loads(message)["close"] == "100.5"
    finally:
        await hub.close()


async def test_hub_unsubscribe_cleans_up_reader() -> None:
    hub = realtime.RealtimeHub(get_redis_client())
    channel = "bars:cleanup"
    queue: asyncio.Queue[str] = asyncio.Queue()
    await hub.subscribe(channel, queue)
    assert channel in hub._readers
    await hub.unsubscribe(channel, queue)
    assert channel not in hub._readers
    await hub.close()
