"""Charting + realtime HTTP/WebSocket endpoints (auth-gated)."""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import numpy as np
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.deps import RedisDep, SessionDep
from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.auth.deps import CurrentUser
from app.modules.backtesting import compute
from app.modules.market_data import realtime, service, signal
from app.modules.market_data import repository as repo
from app.modules.market_data.schemas import (
    BarOut,
    IndicatorSeriesOut,
    InstrumentOut,
    QuoteOut,
    SignalOut,
    WsTicketOut,
)
from app.modules.strategies.spec import IndicatorSpec, StrategySpec

logger = get_logger("market_data")
router = APIRouter(prefix="/market", tags=["market-data"])

_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
_MAX_QUEUE = 1000
# Cap the indicator window so a single request can't pull an unbounded history.
_MAX_INDICATOR_BARS = 1500
_INDICATOR_SPEC_LIST = TypeAdapter(list[IndicatorSpec])

# Multi-output indicators expose one series per output; everything else is "value".
_INDICATOR_OUTPUTS: dict[str, tuple[str, ...]] = {
    "BBANDS": ("upper", "middle", "lower"),
    "MACD": ("macd", "signal", "hist"),
}


def _ensure_utc(value: datetime) -> datetime:
    """Naive query datetime -> UTC (S1). A naive value compared against the
    tz-aware ``ts`` column raises at the driver; assume UTC when omitted."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
    end = _ensure_utc(end) if end is not None else datetime.now(UTC)
    start = _ensure_utc(start) if start is not None else (end - timedelta(days=1))
    if start >= end:
        raise BadRequestError("`start` must be before `end`.")
    bars = await repo.get_bars(session, instrument_id, timeframe=timeframe, start=start, end=end)
    return [BarOut.model_validate(bar) for bar in bars]


def _serialize_series(raw: np.ndarray, timestamps: list[datetime]) -> list[float | None]:
    """NaN warm-up -> null, aligned 1:1 with ``timestamps`` (invariant #4: never
    back-fill fabricated values)."""
    values: list[float | None] = []
    for v in raw:
        f = float(v)
        values.append(None if math.isnan(f) else f)
    return values[: len(timestamps)]


@router.get("/instruments/{instrument_id}/indicators", response_model=list[IndicatorSeriesOut])
async def get_instrument_indicators(
    instrument_id: uuid.UUID,
    session: SessionDep,
    _user: CurrentUser,
    spec: str = Query(description="JSON-encoded list of IndicatorSpec"),
    timeframe: str = Query(default="1h"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> list[IndicatorSeriesOut]:
    """Compute the requested indicators over the instrument's bars.

    Thin wrapper: ``get_bars`` -> ``compute_indicators`` -> serialize (NaN warm-up
    -> null), reusing the exact causal math the backtest engine uses so the chart
    draws what a backtest would read at each bar."""
    if timeframe not in _TIMEFRAMES:
        raise BadRequestError(f"Unsupported timeframe {timeframe!r}.")
    try:
        specs = _INDICATOR_SPEC_LIST.validate_json(spec)
    except ValidationError as exc:
        raise BadRequestError(f"Invalid indicator spec: {exc.errors()[0]['msg']}") from exc
    if not specs:
        return []
    ids = [s.id for s in specs]
    if len(ids) != len(set(ids)):
        raise BadRequestError("Indicator ids must be unique.")

    if await service.get_instrument(session, instrument_id) is None:
        raise NotFoundError()
    end = _ensure_utc(end) if end is not None else datetime.now(UTC)
    start = _ensure_utc(start) if start is not None else (end - timedelta(days=90))
    if start >= end:
        raise BadRequestError("`start` must be before `end`.")
    bars = await repo.get_bars(session, instrument_id, timeframe=timeframe, start=start, end=end)
    bars = bars[-_MAX_INDICATOR_BARS:]
    if not bars:
        return []

    timestamps = [b.ts for b in bars]
    df, _ = compute.build_arrays(bars)
    arrays = compute.compute_indicators(df, specs)

    out: list[IndicatorSeriesOut] = []
    for s in specs:
        for output in _INDICATOR_OUTPUTS.get(s.type, ("value",)):
            key = s.id if output == "value" else f"{s.id}:{output}"
            raw = arrays.get(f"indicator:{key}")
            if raw is None:
                continue
            out.append(
                IndicatorSeriesOut(
                    key=key,
                    id=s.id,
                    type=s.type,
                    output=output,
                    ts=timestamps,
                    values=_serialize_series(raw, timestamps),
                )
            )
    return out


@router.get("/instruments/{instrument_id}/signal", response_model=SignalOut)
async def get_instrument_signal(
    instrument_id: uuid.UUID,
    session: SessionDep,
    _user: CurrentUser,
    spec: str = Query(description="JSON-encoded StrategySpec"),
    equity: str | None = Query(
        default=None, description="Decimal buying power for absolute sizing"
    ),
) -> SignalOut:
    """Evaluate a StrategySpec's entry rule on the latest CLOSED bar.

    entry/stop/target/size are real engine math (invariant #4) via the shared engine
    helpers. The result is an INTENDED order, not executable — live trading is gated
    (invariant #3). Prices must render under a DELAYED DataBadge on the client."""
    try:
        parsed = StrategySpec.model_validate_json(spec)
    except ValidationError as exc:
        raise BadRequestError(f"Invalid strategy spec: {exc.errors()[0]['msg']}") from exc
    equity_dec: Decimal | None = None
    if equity is not None:
        try:
            equity_dec = Decimal(equity)
        except InvalidOperation as exc:
            raise BadRequestError("equity must be a decimal number.") from exc
        if equity_dec <= 0:
            raise BadRequestError("equity must be positive.")

    instrument = await signal.resolve_instrument(session, instrument_id)
    result = await signal.evaluate_signal(session, instrument, parsed, equity=equity_dec)
    return SignalOut(
        should_enter=result.should_enter,
        reference_price=result.reference_price,
        entry=result.entry,
        stop=result.stop,
        target=result.target,
        size=result.size,
        size_per_10k=result.size_per_10k,
        as_of=result.as_of,
        timeframe=result.timeframe,
    )


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
