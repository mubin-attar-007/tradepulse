"""PUBLIC, unauthenticated read API that powers the per-ticker SEO pages.

No ``CurrentUser`` dependency: these endpoints are crawlable and serve only data
that is already public (delayed prices) or hypothetical (the reference backtest).
Everything here is DELAYED market data — the frontend renders prices under a
DELAYED DataBadge and the reference backtest under the HypotheticalBanner (product
invariant #3). All money is a Decimal-string ``Money`` serialized server-side
(invariant #2).

URL slugs are case-insensitive and accept a hyphen for the crypto pair separator
(``/public/markets/btc-usd`` -> ``BTC/USD``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.core.deps import SessionDep
from app.core.errors import BadRequestError, NotFoundError
from app.modules.market_data import reference_backtest, service
from app.modules.market_data import repository as repo
from app.modules.market_data.schemas import (
    PublicChartBar,
    PublicIndicatorSeries,
    PublicInstrumentSummary,
    PublicMarketOut,
    PublicPricePoint,
    PublicReferenceSummary,
    PublicTrackRecordComponent,
    PublicTrackRecordOut,
)

router = APIRouter(prefix="/public/markets", tags=["public-markets"])

# The track record lives at its own top-level public path (not under /markets/{ticker})
# because it is a universe-wide aggregate, not a per-ticker resource.
track_record_router = APIRouter(prefix="/public", tags=["public-markets"])

# Annualized metrics are meaningless — and wildly misleading (billion-percent CAGR) —
# over the tiny bar samples the reference backtest may run on, and these numbers are
# rendered on crawlable SEO pages. Strip them from every PUBLIC surface (B4/S3); the
# authed app keeps them (real users see the caveats). We keep only per-run, non-
# annualized metrics: total_return, max_drawdown, win_rate, num_trades, etc.
_ANNUALIZED_METRICS = frozenset({"cagr", "sharpe", "sortino"})


def _public_metrics(metrics: dict[str, float]) -> dict[str, float]:
    """Drop annualized metrics that mislead over short/limited samples (B4)."""
    return {k: v for k, v in metrics.items() if k not in _ANNUALIZED_METRICS}


@track_record_router.get("/track-record", response_model=PublicTrackRecordOut)
async def get_public_track_record(session: SessionDep) -> PublicTrackRecordOut:
    """Curated, caveated aggregate of the reference backtest across the universe.

    HYPOTHETICAL: the frontend must render this under the HypotheticalBanner. Every
    number is real ``compute_metrics()`` output; the aggregate is an equal-weight,
    per-run average across covered symbols (never compounded, never a real return)."""
    tr = await reference_backtest.get_track_record(session)
    return PublicTrackRecordOut(
        available=tr.available,
        strategy=tr.strategy,
        timeframe=tr.timeframe,
        spec_hash=tr.spec_hash,
        engine_version=tr.engine_version,
        symbols_covered=tr.symbols_covered,
        symbols_total=tr.symbols_total,
        total_bars=tr.total_bars,
        metrics=_public_metrics(tr.metrics),
        components=[
            PublicTrackRecordComponent(
                symbol=c.symbol,
                bars=c.bars,
                start=c.start,
                end=c.end,
                metrics=_public_metrics(c.metrics),
            )
            for c in tr.components
        ],
        commission_bps=tr.commission_bps,
        slippage_bps=tr.slippage_bps,
        note=tr.note,
        data_note=tr.data_note,
    )

_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
# Bars pulled to compute the on-page indicator series. Enough to warm up a 20-period
# indicator with room to spare, capped so the public payload stays small.
_INDICATOR_BARS = 500

# Hard row cap on the public bars payload — mirrors the authed router's
# _MAX_INDICATOR_BARS so an anonymous caller can't pull an unbounded history (B3).
_MAX_PUBLIC_BARS = 1500

# Per-timeframe max query span (B3). Attacker-controlled start/end otherwise let a
# 1m request full-scan a month of raw bars. Each cap is chosen so a legit chart
# window fits well inside ~_MAX_PUBLIC_BARS bars for that timeframe.
_MAX_SPAN: dict[str, timedelta] = {
    "1m": timedelta(days=2),
    "5m": timedelta(days=7),
    "15m": timedelta(days=21),
    "1h": timedelta(days=90),
    "4h": timedelta(days=365),
    "1d": timedelta(days=365 * 5),
}


def _ensure_utc(value: datetime) -> datetime:
    """Naive query datetime -> UTC (S1). A naive value compared against the
    tz-aware ``ts`` column raises at the driver; assume UTC for public callers."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _normalize_slug(ticker: str) -> str:
    """Public URL slug -> canonical symbol candidate.

    A hyphen in a crypto slug maps to the pair separator (``btc-usd`` -> ``BTC/USD``).
    Equity tickers contain no hyphen, so they pass through unchanged. Final matching
    is case-insensitive in the resolver."""
    return ticker.replace("-", "/")


@router.get("", response_model=list[PublicInstrumentSummary])
async def list_public_markets(session: SessionDep) -> list[PublicInstrumentSummary]:
    """Catalog of tickers available on the public pages."""
    rows = await service.list_instruments(session)
    return [
        PublicInstrumentSummary(ticker=r.symbol, name=r.name, asset_class=r.asset_class)
        for r in rows
    ]


@router.get("/{ticker}", response_model=PublicMarketOut)
async def get_public_market(ticker: str, session: SessionDep) -> PublicMarketOut:
    """The full per-ticker bundle: meta + latest (delayed) price + real indicator
    series + the reference-backtest summary."""
    instrument = await service.resolve_symbol(session, _normalize_slug(ticker))
    if instrument is None:
        raise NotFoundError(f"Unknown ticker {ticker!r}.")

    timeframe = reference_backtest.REFERENCE_TIMEFRAME
    end = datetime.now(UTC)
    start = end - timedelta(days=90)
    bars = await repo.get_bars(session, instrument.id, timeframe=timeframe, start=start, end=end)
    bars = bars[-_INDICATOR_BARS:]

    indicators = [
        PublicIndicatorSeries(key=key, label=label, values=values)
        for key, label, values in reference_backtest.compute_public_indicators(bars)
    ]

    # Latest real price: the most recent CLOSED bar (delayed). None when we hold no
    # history yet for this instrument.
    latest_bar = await repo.latest_bar(session, instrument.id)
    latest = (
        PublicPricePoint(price=latest_bar.close, as_of=latest_bar.ts)
        if latest_bar is not None
        else None
    )

    summary = await reference_backtest.get_reference_summary(session, instrument)
    reference = PublicReferenceSummary(
        available=summary.available,
        strategy=summary.strategy,
        timeframe=summary.timeframe,
        spec_hash=summary.spec_hash,
        engine_version=summary.engine_version,
        bars=summary.bars,
        start=summary.start,
        end=summary.end,
        metrics=_public_metrics(summary.metrics),
        note=summary.note,
    )

    return PublicMarketOut(
        instrument=PublicInstrumentSummary(
            ticker=instrument.symbol, name=instrument.name, asset_class=instrument.asset_class
        ),
        exchange=instrument.exchange,
        quote_currency=instrument.quote_currency,
        timeframe=timeframe,
        latest=latest,
        indicators=indicators,
        reference_backtest=reference,
    )


@router.get("/{ticker}/bars", response_model=list[PublicChartBar])
async def get_public_bars(
    ticker: str,
    session: SessionDep,
    timeframe: str = Query(default="1h"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> list[PublicChartBar]:
    """OHLCV history for the public chart (reuses the shared ``get_bars`` reader).

    Anonymous surface, so the window is bounded (B3): naive datetimes are read as
    UTC (S1), ``start`` must precede ``end``, the span may not exceed a per-timeframe
    max, and the payload is hard-capped at ``_MAX_PUBLIC_BARS`` rows."""
    if timeframe not in _TIMEFRAMES:
        raise BadRequestError(f"Unsupported timeframe {timeframe!r}.")
    instrument = await service.resolve_symbol(session, _normalize_slug(ticker))
    if instrument is None:
        raise NotFoundError(f"Unknown ticker {ticker!r}.")
    end = _ensure_utc(end) if end is not None else datetime.now(UTC)
    # Default window per timeframe keeps a bare request cheap (was a flat 30 days,
    # which on 1m was a full-month scan).
    max_span = _MAX_SPAN[timeframe]
    start = _ensure_utc(start) if start is not None else (end - min(max_span, timedelta(days=30)))
    if start >= end:
        raise BadRequestError("`start` must be before `end`.")
    if end - start > max_span:
        raise BadRequestError(
            f"Requested span too large for {timeframe}: max {max_span.days} day(s)."
        )
    bars = await repo.get_bars(
        session, instrument.id, timeframe=timeframe, start=start, end=end, limit=_MAX_PUBLIC_BARS
    )
    return [
        PublicChartBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)
        for b in bars
    ]
