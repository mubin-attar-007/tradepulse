"""Research-surface API schemas.

These are the response shapes for surfaces COMPOSED from market data + the
strategy DSL + the backtest engine: point-in-time signal evaluation and the
public per-ticker illustration. They live here (not in market_data) because
they describe research output, not raw market data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.types import Money


class SignalOut(BaseModel):
    """Point-in-time evaluation of a StrategySpec's entry rule on the latest CLOSED
    bar. All money is a server-serialized Decimal string (invariant #2).

    This is an INTENDED order, not an executable one — live trading is gated (POST
    /live/orders returns 403). The client must render prices under a DELAYED
    DataBadge (invariant #3). ``entry``/``stop``/``target``/``size`` are real engine
    math (invariant #4); ``size`` is present only when the caller supplied equity,
    while ``size_per_10k`` (units per $10,000 of buying power) is always present so
    the client never multiplies a price client-side."""

    should_enter: bool
    reference_price: Money
    entry: Money
    stop: Money | None
    target: Money | None
    size: Money | None
    size_per_10k: Money
    as_of: datetime
    timeframe: str


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
    metrics: dict[str, float | None]
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


class PublicTrackRecordComponent(BaseModel):
    """One symbol's reference run inside the aggregate track record.

    HYPOTHETICAL / backtested — render under the HypotheticalBanner with the rest."""

    symbol: str
    bars: int
    start: datetime | None
    end: datetime | None
    metrics: dict[str, float | None]


class PublicTrackRecordOut(BaseModel):
    """The curated, caveated landing-page track record.

    An equal-weight, per-run AVERAGE of the reference SMA-crossover backtest across the
    covered universe — NOT a portfolio, NOT compounded, NOT a real/achievable return.
    HYPOTHETICAL: always render under the HypotheticalBanner. ``provenance`` fields
    (``engine_version``, ``commission_bps``, ``slippage_bps``, ``data_note``) make the
    number reproducible."""

    available: bool
    strategy: str
    timeframe: str
    spec_hash: str
    engine_version: str
    symbols_covered: int
    symbols_total: int
    total_bars: int
    metrics: dict[str, float | None]
    components: list[PublicTrackRecordComponent]
    commission_bps: float
    slippage_bps: float
    note: str
    data_note: str
