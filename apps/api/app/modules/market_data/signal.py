"""Point-in-time signal evaluation for a StrategySpec against the latest bars.

This powers the F2 signal card: given a spec and an instrument, does the entry
rule fire on the most recently CLOSED bar, and if it did, what entry / stop /
target / size would the engine intend?

HONESTY (product invariants #2, #3, #4):
  * Every number is real engine math. The fill/stop/target come from the SHARED
    helpers in :mod:`app.modules.backtesting.engine` (``entry_fill`` /
    ``stop_from_fill`` / ``target_from_fill``) and the size from the engine's
    ``size_for_entry`` — this module NEVER reimplements the formulas.
  * ``should_enter`` is the same ``compute.evaluate(spec.entry_long, …)`` the
    engine reads at a closed bar, so it can never look ahead.
  * The reference price is the latest CLOSED bar's close (delayed). The engine
    would really fill at the NEXT bar's open, which does not exist yet for a live
    signal; we use the last close as the honest best estimate and nudge it by the
    engine's adverse-slippage fraction. The result is an *intended* order, NOT an
    executable one — live trading stays gated (POST /live/orders → 403).
  * Money never crosses the wire as a float. Size is returned both at the caller's
    equity (when supplied) and as ``size_per_10k`` (size at a canonical $10,000 of
    buying power) so the client never multiplies a price by anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.modules.backtesting import compute, engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.strategies.spec import StrategySpec

# Canonical buying power for the equity-independent size (so the client never does
# money math): "how many units per $10,000 of equity".
_SIZE_BASIS = Decimal("10000")

# Enough recent history to warm up the spec's indicators with room for a couple of
# cross events; the engine only ever needs a causal window ending at the last bar.
_LOOKBACK = timedelta(days=365)
_MIN_BARS = 2


@dataclass(frozen=True, slots=True)
class Signal:
    """The intended (NOT executable) long entry implied by ``spec`` on the latest
    closed bar. ``size`` is present only when the caller supplied equity."""

    should_enter: bool
    reference_price: Decimal
    entry: Decimal
    stop: Decimal | None
    target: Decimal | None
    size: Decimal | None
    size_per_10k: Decimal
    as_of: datetime
    timeframe: str


def _latest_atr(spec: StrategySpec, arrays: compute.PriceArrays, i: int) -> float | None:
    """The spec's ATR-ref value at bar ``i`` (for ATR sizing), else None."""
    if spec.sizing.method != "atr" or not spec.sizing.atr_ref:
        return None
    arr = arrays.get(f"indicator:{spec.sizing.atr_ref}")
    if arr is None:
        return None
    value = float(arr[i])
    return value if value == value else None  # NaN during warm-up -> None


async def evaluate_signal(
    session: AsyncSession,
    instrument: Instrument,
    spec: StrategySpec,
    *,
    equity: Decimal | None = None,
    config: ExecutionConfig | None = None,
) -> Signal:
    """Evaluate ``spec``'s entry rule on the most recent CLOSED bar for
    ``instrument`` and return the engine's intended entry/stop/target/size."""
    config = config or ExecutionConfig()
    end = datetime.now(UTC)
    bars = await md_repo.get_bars(
        session, instrument.id, timeframe=spec.timeframe, start=end - _LOOKBACK, end=end
    )
    if len(bars) < _MIN_BARS:
        raise BadRequestError(
            "Not enough bars to evaluate a signal for this instrument; backfill more history."
        )

    df, arrays = compute.build_arrays(bars)
    arrays.update(compute.compute_indicators(df, spec.indicators))

    last = len(bars) - 1
    should_enter = compute.evaluate(spec.entry_long, arrays, last)

    # Reference = last CLOSED bar's close (delayed). The engine fills the next bar's
    # open; that bar does not exist yet, so the close is the honest estimate.
    reference_price = bars[last].close
    slip = engine.slippage_fraction(config)
    fill = engine.entry_fill(reference_price, slip)
    exit_rule = spec.exit
    stop = engine.stop_from_fill(fill, exit_rule)
    target = engine.target_from_fill(fill, exit_rule)
    atr_val = _latest_atr(spec, arrays, last)

    size = engine.size_for_entry(spec, equity, fill, atr_val) if equity is not None else None
    size_per_10k = engine.size_for_entry(spec, _SIZE_BASIS, fill, atr_val)

    return Signal(
        should_enter=should_enter,
        reference_price=reference_price,
        entry=fill,
        stop=stop,
        target=target,
        size=size,
        size_per_10k=size_per_10k,
        as_of=bars[last].ts,
        timeframe=spec.timeframe,
    )


async def resolve_instrument(session: AsyncSession, instrument_id: object) -> Instrument:
    """Fetch an active instrument or raise 404."""
    instrument = await session.get(Instrument, instrument_id)
    if instrument is None:
        raise NotFoundError()
    return instrument
