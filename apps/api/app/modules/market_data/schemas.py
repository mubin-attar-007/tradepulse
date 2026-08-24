"""Market-data API response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.types import Money


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    asset_class: str
    name: str | None
    exchange: str | None
    quote_currency: str
    calendar: str


class BarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    open: Money
    high: Money
    low: Money
    close: Money
    volume: Money


class QuoteOut(BaseModel):
    instrument_id: uuid.UUID
    price: Money


class WsTicketOut(BaseModel):
    ticket: str
    expires_in: int


# --- F2: on-chart indicators + signal card (auth-gated) ------------------------


class IndicatorSeriesOut(BaseModel):
    """One computed indicator series aligned 1:1 with the requested bars.

    ``values`` carries ``null`` during the indicator's warm-up window (the first
    N-1 points of an N-period indicator) so the client draws honest gaps instead of
    fabricated values. Multi-output indicators (BBANDS, MACD) surface one entry per
    output, keyed ``<id>:<output>`` (e.g. ``bb:upper``, ``macd:hist``)."""

    key: str  # operand key: "<id>" or "<id>:<output>"
    id: str  # the requesting IndicatorSpec id
    type: str  # EMA | SMA | RSI | ATR | BBANDS | MACD | VWAP | VOL_SMA
    output: str  # "value" for single-output, else the sub-series name
    ts: list[datetime]  # bar timestamps (parallel to values)
    values: list[float | None]
