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


# --- Public (unauthenticated) per-ticker SEO surface ---------------------------


class PublicInstrumentSummary(BaseModel):
    """Row for the public catalog (`GET /public/markets`)."""

    ticker: str
    name: str | None
    asset_class: str


class PublicIndicatorSeries(BaseModel):
    """A single indicator's series aligned 1:1 with the bar timestamps.

    ``values`` may contain ``null`` during the indicator's warm-up window (e.g. the
    first N-1 points of an N-period SMA), so the frontend can render gaps honestly
    rather than back-filling fabricated values."""

    key: str  # e.g. "SMA_20", "EMA_20", "RSI_14"
    label: str
    values: list[float | None]


class PublicPricePoint(BaseModel):
    """Latest real (delayed) price + its as-of timestamp. Always render under a
    DELAYED DataBadge (product invariant #3)."""

    price: Money
    as_of: datetime


class PublicReferenceSummary(BaseModel):
    """Reference-backtest summary for the public page.

    HYPOTHETICAL / backtested — must sit under the HypotheticalBanner. Carries the
    spec name + hash so the illustration is reproducible, never a bare claim."""

    available: bool
    strategy: str
    timeframe: str
    spec_hash: str
    engine_version: str
    bars: int
    start: datetime | None
    end: datetime | None
    metrics: dict[str, float]
    note: str


class PublicChartBar(BaseModel):
    """OHLCV bar timestamp + values (timestamps parallel the indicator series)."""

    ts: datetime
    open: Money
    high: Money
    low: Money
    close: Money
    volume: Money


class PublicMarketOut(BaseModel):
    """Everything the public per-ticker page needs in one bundle."""

    instrument: PublicInstrumentSummary
    exchange: str | None
    quote_currency: str
    timeframe: str
    latest: PublicPricePoint | None
    indicators: list[PublicIndicatorSeries]
    reference_backtest: PublicReferenceSummary
