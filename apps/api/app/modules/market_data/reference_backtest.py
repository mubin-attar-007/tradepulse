"""The single canonical, honest reference backtest per symbol.

ONE simple, transparent strategy — a classic SMA(10)/SMA(30) crossover with a
protective stop and a fixed profit target — is run through the SAME event-driven
engine that powers user backtests (:mod:`app.modules.backtesting.engine`). No
special-casing, no cherry-picked window: it runs over ALL closed bars we hold for
the symbol, at a fixed timeframe, with realistic commission + slippage.

This is deliberately un-optimized. It exists to give the public per-ticker pages a
*reproducible, caveated* illustration of the platform's methodology — NOT a trade
recommendation. F4 (the marketing/methodology surface) consumes the exact same
summary via :func:`get_reference_summary`, so the number a visitor sees is the
number the engine actually produced.

Honesty guarantees:
  * every metric comes from ``compute_metrics()`` over a real engine run;
  * the spec is embedded in the summary (``strategy`` + ``spec_hash``) so anyone
    can reproduce it;
  * results are hypothetical/backtested and must be presented under the
    HypotheticalBanner (product invariant #3) — this module never implies a real
    return.

Caching: results are memoized per ``(symbol, data_fingerprint)``. The fingerprint
changes whenever the underlying bars change, so a backfill transparently
invalidates the cache without a manual flush. The cache is per-process in-memory
(sufficient for the read-heavy public pages; a cold process simply recomputes).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.backtesting import compute, engine
from app.modules.backtesting.service import _fingerprint
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data import service as md_service
from app.modules.market_data.models import Instrument
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
    Timeframe,
)

logger = get_logger("reference_backtest")

# The reference runs at a fixed timeframe for every symbol. 1h balances "enough
# bars for a 30-period slow SMA to warm up" against the modest history a free-tier
# backfill pulls (a few days of 1-minute bars aggregate to dozens of hourly bars).
REFERENCE_TIMEFRAME: Timeframe = "1h"

# How far back we look for bars. Generous upper bound; the engine simply uses
# whatever closed bars exist in the window (never fabricates missing history).
_LOOKBACK = timedelta(days=365)

_FAST_PERIOD = 10
_SLOW_PERIOD = 30
# Minimum bars for the slow SMA to warm up AND leave room for at least a couple of
# crossovers; below this the summary is honestly reported as "insufficient data".
_MIN_BARS = _SLOW_PERIOD + 5


# A few standard, real indicators surfaced on the public chart. Each entry is
# (operand-key, response-key, label, IndicatorSpec) — computed causally by
# compute_indicators (identical math to the backtest engine, no look-ahead).
_PUBLIC_INDICATORS: list[tuple[str, str, IndicatorSpec]] = [
    ("SMA_20", "SMA 20", IndicatorSpec(id="sma20", type="SMA", params={"period": 20})),
    ("EMA_20", "EMA 20", IndicatorSpec(id="ema20", type="EMA", params={"period": 20})),
    ("RSI_14", "RSI 14", IndicatorSpec(id="rsi14", type="RSI", params={"period": 14})),
]


def compute_public_indicators(
    bars: Sequence[BarPoint],
) -> list[tuple[str, str, list[float | None]]]:
    """Real SMA/EMA/RSI series aligned 1:1 with ``bars`` (NaN warm-up -> None).

    Uses the SAME causal ``compute_indicators`` the engine uses, so what the public
    chart draws is exactly what a backtest would read at each bar."""
    if not bars:
        return []
    df, _ = compute.build_arrays(bars)
    specs = [spec for _, _, spec in _PUBLIC_INDICATORS]
    arrays = compute.compute_indicators(df, specs)
    series: list[tuple[str, str, list[float | None]]] = []
    for key, label, spec in _PUBLIC_INDICATORS:
        raw = arrays.get(f"indicator:{spec.id}")
        if raw is None:
            continue
        values = [None if math.isnan(float(v)) else float(v) for v in raw]
        series.append((key, label, values))
    return series


def build_reference_spec(symbol: str) -> StrategySpec:
    """The ONE canonical reference StrategySpec for ``symbol``.

    Identical shape for every instrument (only the universe differs), so it is
    trivially reproducible and comparable across tickers: go long when the fast
    SMA crosses above the slow SMA; exit on the reverse cross, a 5% stop, or a 10%
    target. Fixed 20%-of-equity sizing keeps it simple and un-leveraged.
    """
    return StrategySpec(
        name=f"Reference SMA {_FAST_PERIOD}/{_SLOW_PERIOD} crossover ({symbol})",
        universe=[symbol],
        timeframe=REFERENCE_TIMEFRAME,
        indicators=[
            IndicatorSpec(id="sma_fast", type="SMA", params={"period": _FAST_PERIOD}),
            IndicatorSpec(id="sma_slow", type="SMA", params={"period": _SLOW_PERIOD}),
        ],
        entry_long=Comparison(
            left=Operand(kind="indicator", ref="sma_fast"),
            op="cross_above",
            right=Operand(kind="indicator", ref="sma_slow"),
        ),
        exit=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            exit_conditions=Comparison(
                left=Operand(kind="indicator", ref="sma_fast"),
                op="cross_below",
                right=Operand(kind="indicator", ref="sma_slow"),
            ),
        ),
        sizing=PositionSizing(method="percent_equity", value=0.20),
        risk=RiskLimits(max_position_pct=0.20, max_open_positions=1),
    )


@dataclass(frozen=True, slots=True)
class ReferenceSummary:
    """The cached, JSON-safe reference-backtest summary for one symbol."""

    symbol: str
    timeframe: str
    strategy: str
    spec_hash: str
    engine_version: str
    data_fingerprint: str
    bars: int
    start: datetime | None
    end: datetime | None
    metrics: dict[str, float] = field(default_factory=dict)
    available: bool = True
    note: str = ""


# (symbol, data_fingerprint) -> summary. The fingerprint keys the entry so a
# backfill (which changes the bars) auto-invalidates the stale result.
_CACHE: dict[tuple[str, str], ReferenceSummary] = {}


def _unavailable(symbol: str, note: str) -> ReferenceSummary:
    return ReferenceSummary(
        symbol=symbol,
        timeframe=REFERENCE_TIMEFRAME,
        strategy=build_reference_spec(symbol).name,
        spec_hash="",
        engine_version="",
        data_fingerprint="",
        bars=0,
        start=None,
        end=None,
        metrics={},
        available=False,
        note=note,
    )


async def get_reference_summary(session: AsyncSession, instrument: Instrument) -> ReferenceSummary:
    """Run (or return the cached) reference backtest for ``instrument``.

    Uses the shared engine over ALL closed bars in the lookback window. Metrics are
    straight from ``compute_metrics()`` (via the engine's result). Caveated: when
    there are too few bars to warm up the slow SMA, returns an ``available=False``
    summary rather than a misleading zero-return."""
    symbol = instrument.symbol
    end = datetime.now(UTC)
    start = end - _LOOKBACK

    bars = await md_repo.get_bars(
        session, instrument.id, timeframe=REFERENCE_TIMEFRAME, start=start, end=end
    )
    if len(bars) < _MIN_BARS:
        return _unavailable(
            symbol,
            f"Not enough {REFERENCE_TIMEFRAME} history ({len(bars)} bars) to run the "
            f"reference SMA {_FAST_PERIOD}/{_SLOW_PERIOD} strategy; backfill more data.",
        )

    fingerprint = _fingerprint(instrument.id, REFERENCE_TIMEFRAME, bars)
    cached = _CACHE.get((symbol, fingerprint))
    if cached is not None:
        return cached

    spec = build_reference_spec(symbol)
    # Realistic frictions (default commission + slippage) — never frictionless.
    result = engine.run(spec, bars, ExecutionConfig())
    summary = ReferenceSummary(
        symbol=symbol,
        timeframe=REFERENCE_TIMEFRAME,
        strategy=spec.name,
        spec_hash=spec.spec_hash(),
        engine_version=result.engine_version,
        data_fingerprint=fingerprint,
        bars=result.bars,
        start=bars[0].ts,
        end=bars[-1].ts,
        metrics=result.metrics,
        available=True,
        note=(
            "Hypothetical, un-optimized illustration of platform methodology over "
            "delayed historical data. Not a recommendation or a real return."
        ),
    )
    _CACHE[(symbol, fingerprint)] = summary
    logger.info(
        "reference_backtest_computed",
        symbol=symbol,
        bars=result.bars,
        spec_hash=summary.spec_hash,
    )
    return summary


# --- Public track record (aggregate across the seeded universe) -----------------
#
# The landing page shows ONE curated, caveated "track record": the same reference
# SMA crossover run through the SAME engine over every instrument for which we hold
# enough history. It is NOT a portfolio, NOT compounded, NOT a real return — it is a
# per-run illustration of the platform's own backtest engine, aggregated only so the
# landing page can show a real number instead of a fabricated one (invariant #4). Each
# component summary is real ``compute_metrics()`` output; the "aggregate" is a simple,
# transparent average of per-run metrics across the covered symbols.

_AGGREGATED_METRICS = ("total_return", "cagr", "sharpe", "sortino", "max_drawdown", "win_rate")

_DATA_NOTE = (
    "Runs over the DELAYED historical bars held for each instrument (polled market "
    "data, not a real-time SIP feed). Only symbols with enough history to warm up the "
    "slow SMA are included; coverage grows as more data is backfilled."
)


@dataclass(frozen=True, slots=True)
class TrackRecordComponent:
    """One symbol's contribution to the aggregate (a single reference run)."""

    symbol: str
    bars: int
    start: datetime | None
    end: datetime | None
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class TrackRecord:
    """The curated, caveated public track record.

    ``metrics`` is the mean of each metric across ``components`` (equal-weight, per-run,
    NOT compounded). ``provenance`` carries the exact engine settings so the number is
    reproducible. Every consumer must render this under the HypotheticalBanner."""

    available: bool
    strategy: str
    timeframe: str
    spec_hash: str
    engine_version: str
    symbols_covered: int
    symbols_total: int
    total_bars: int
    metrics: dict[str, float]
    components: list[TrackRecordComponent]
    commission_bps: float
    slippage_bps: float
    note: str
    data_note: str


def _empty_track_record(strategy: str, symbols_total: int, note: str) -> TrackRecord:
    cfg = ExecutionConfig()
    return TrackRecord(
        available=False,
        strategy=strategy,
        timeframe=REFERENCE_TIMEFRAME,
        spec_hash="",
        engine_version="",
        symbols_covered=0,
        symbols_total=symbols_total,
        total_bars=0,
        metrics={},
        components=[],
        commission_bps=cfg.commission_bps,
        slippage_bps=cfg.slippage_bps,
        note=note,
        data_note=_DATA_NOTE,
    )


async def get_track_record(session: AsyncSession) -> TrackRecord:
    """Aggregate the per-symbol reference backtests across the seeded universe.

    Averages real ``compute_metrics()`` output across every instrument with enough
    history. Honest by construction: no cherry-picking (ALL covered symbols count),
    no compounding (per-run average), realistic frictions (default commission +
    slippage), and an ``available=False`` result when nothing has enough data yet."""
    instruments = await md_service.list_instruments(session)
    symbols_total = len(instruments)
    strategy = f"Reference SMA {_FAST_PERIOD}/{_SLOW_PERIOD} crossover"

    components: list[TrackRecordComponent] = []
    spec_hash = ""
    engine_version = ""
    total_bars = 0
    for instrument in instruments:
        summary = await get_reference_summary(session, instrument)
        if not summary.available:
            continue
        spec_hash = spec_hash or summary.spec_hash
        engine_version = engine_version or summary.engine_version
        total_bars += summary.bars
        components.append(
            TrackRecordComponent(
                symbol=summary.symbol,
                bars=summary.bars,
                start=summary.start,
                end=summary.end,
                metrics=summary.metrics,
            )
        )

    if not components:
        return _empty_track_record(
            strategy,
            symbols_total,
            "No instrument has enough history yet to run the reference strategy; "
            "backfill market data to populate the track record.",
        )

    aggregate: dict[str, float] = {}
    for key in _AGGREGATED_METRICS:
        values = [c.metrics[key] for c in components if key in c.metrics]
        if values:
            aggregate[key] = round(sum(values) / len(values), 6)
    # Trades are summed (a count), not averaged.
    aggregate["num_trades"] = float(
        sum(int(c.metrics.get("num_trades", 0)) for c in components)
    )

    cfg = ExecutionConfig()
    return TrackRecord(
        available=True,
        strategy=strategy,
        timeframe=REFERENCE_TIMEFRAME,
        spec_hash=spec_hash,
        engine_version=engine_version,
        symbols_covered=len(components),
        symbols_total=symbols_total,
        total_bars=total_bars,
        metrics=aggregate,
        components=components,
        commission_bps=cfg.commission_bps,
        slippage_bps=cfg.slippage_bps,
        note=(
            "Hypothetical, un-optimized illustration of the platform's own backtest "
            "engine — the same SMA crossover run across every covered instrument. "
            "Per-run, equal-weight average; NOT a portfolio, NOT compounded, NOT a real "
            "or achievable return, and not a recommendation."
        ),
        data_note=_DATA_NOTE,
    )
