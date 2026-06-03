"""Charting + realtime HTTP/WebSocket endpoints (auth-gated)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.deps import RedisDep, SessionDep
from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.auth.deps import CurrentUser
from app.modules.market_data import realtime, service
from app.modules.market_data import repository as repo
from app.modules.market_data.schemas import BarOut, InstrumentOut, QuoteOut, WsTicketOut

logger = get_logger("market_data")
router = APIRouter(prefix="/market", tags=["market-data"])

_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
_MAX_QUEUE = 1000


@router.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(
    session: SessionDep,
    _user: CurrentUser,
    asset_class: str | None = Query(default=None),
) -> list[InstrumentOut]:
    rows = await service.list_instruments(session, asset_class=asset_class)
    return [InstrumentOut.model_validate(row) for row in rows]


@router.get("/instruments/{instrument_id}/bars", response_model=list[BarOut])
async def get_instrument_bars(
    instrument_id: uuid.UUID,
    session: SessionDep,
    _user: CurrentUser,
    timeframe: str = Query(default="1m"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> list[BarOut]:
    if timeframe not in _TIMEFRAMES:
        raise BadRequestError(f"Unsupported timeframe {timeframe!r}.")
    if await service.get_instrument(session, instrument_id) is None:
        raise NotFoundError()
    end = end or datetime.now(UTC)
    start = start or (end - timedelta(days=1))
    bars = await repo.get_bars(session, instrument_id, timeframe=timeframe, start=start, end=end)
    return [BarOut.model_validate(bar) for bar in bars]


@router.get("/instruments/{instrument_id}/latest", response_model=QuoteOut)
async def latest_quote(
    instrument_id: uuid.UUID,
    session: SessionDep,
    redis: RedisDep,
    _user: CurrentUser,
) -> QuoteOut:
    price = await realtime.get_latest_price(redis, instrument_id)
    if price is None:
        bar = await repo.latest_bar(session, instrument_id)
        if bar is None:
            raise NotFoundError()
        price = bar.close
    return QuoteOut(instrument_id=instrument_id, price=price)


@router.post("/ws-ticket", response_model=WsTicketOut)
async def create_ws_ticket(redis: RedisDep, user: CurrentUser) -> WsTicketOut:
    ticket = await realtime.issue_ws_ticket(redis, user.id)
    return WsTicketOut(ticket=ticket, expires_in=realtime.TICKET_TTL)


@router.websocket("/ws")
async def market_ws(websocket: WebSocket, redis: RedisDep, ticket: str = Query()) -> None:
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in get_settings().cors_origins:
        await websocket.close(code=4403)
        return
    user_id = await realtime.redeem_ws_ticket(redis, ticket)
    if user_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    hub = realtime.get_hub()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_MAX_QUEUE)
    channels: set[str] = set()

    async def pump() -> None:
        while True:
            await websocket.send_text(await queue.get())

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            raw_id = message.get("instrument_id")
            if not raw_id:
                continue
            try:
                channel = realtime.bars_channel(uuid.UUID(raw_id))
            except ValueError:
                continue
            if action == "subscribe" and channel not in channels:
                channels.add(channel)
                await hub.subscribe(channel, queue)
            elif action == "unsubscribe" and channel in channels:
                channels.discard(channel)
                await hub.unsubscribe(channel, queue)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        for channel in channels:
            await hub.unsubscribe(channel, queue)
