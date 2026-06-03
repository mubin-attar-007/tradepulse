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
