"""Property-based invariants.

Fixtures pin known cases; these assert what must be true for EVERY input. Each
property below corresponds to a way the engine could be wrong that a hand-written
case would probably miss.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.modules.backtesting import engine
from app.modules.backtesting.types import BacktestResult, ExecutionConfig
from app.modules.market_data.repository import BarPoint
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 1, 2, tzinfo=UTC)
_SETTINGS = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def scenario(draw: st.DrawFn) -> tuple[StrategySpec, list[BarPoint], ExecutionConfig]:
    n = draw(st.integers(min_value=5, max_value=60))
    closes = draw(st.lists(st.integers(min_value=5000, max_value=15000), min_size=n, max_size=n))
    bars: list[BarPoint] = []
    prev = Decimal(closes[0]) / 100
    for i, raw in enumerate(closes):
        close = Decimal(raw) / 100
        o = prev
        pad_h = Decimal(draw(st.integers(min_value=0, max_value=200))) / 100
        pad_l = Decimal(draw(st.integers(min_value=0, max_value=200))) / 100
        bars.append(
            BarPoint(
                ts=BASE + timedelta(minutes=i),
                open=o,
                high=max(o, close) + pad_h,
                low=max(min(o, close) - pad_l, Decimal("0.01")),
                close=close,
                volume=Decimal(draw(st.integers(min_value=1, max_value=100000))),
                bar_count=1,
            )
        )
        prev = close

    method = draw(st.sampled_from(["fixed_units", "percent_equity", "risk_per_trade"]))
    stop = draw(st.integers(min_value=1, max_value=40)) / 100
    sizing = PositionSizing(
        method=method,  # type: ignore[arg-type]
        value=draw(st.integers(min_value=1, max_value=90)) / 100
        if method != "fixed_units"
        else draw(st.integers(min_value=1, max_value=200)),
    )
    spec = StrategySpec(
        name="prop",
        universe=["X"],
        timeframe="1m",
        indicators=[IndicatorSpec(id="sma", type="SMA", params={"period": 3})],
        entry_long=Comparison(
            left=Operand(kind="price", field="close"),
            op=draw(st.sampled_from([">", "cross_above"])),
            right=Operand(kind="indicator", ref="sma"),
        ),
        exit=ExitRule(
            # risk_per_trade requires a stop, so always supply one.
            stop_loss_pct=stop,
            take_profit_pct=draw(st.integers(min_value=1, max_value=40)) / 100,
            time_exit_bars=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=10))),
        ),
        sizing=sizing,
        risk=RiskLimits(
            max_position_pct=draw(st.integers(min_value=1, max_value=100)) / 100,
            max_open_positions=1,
            max_consecutive_losses=draw(
                st.one_of(st.none(), st.integers(min_value=1, max_value=5))
            ),
        ),
    )
    config = ExecutionConfig(
        commission_bps=draw(st.sampled_from([0.0, 1.0, 2.0, 25.0])),
        slippage_bps=draw(st.sampled_from([0.0, 1.0, 10.0])),
        initial_cash=Decimal("100000"),
    )
    return spec, bars, config


def _run(scn: tuple[StrategySpec, list[BarPoint], ExecutionConfig]) -> BacktestResult:
    spec, bars, config = scn
    return engine.run(spec, bars, config)


@_SETTINGS
@given(scn=scenario())
def test_accounting_identity(scn) -> None:  # type: ignore[no-untyped-def]
    """initial cash + realized P&L == final equity, to sub-cent.

    The engine flattens at the end, so once every position is closed the equity
    curve's last point IS cash, and cash can only have moved by realized P&L. Any
    residual beyond Decimal's 28-digit rounding means money was created or lost
    somewhere in the fill/commission path.
    """
    result = _run(scn)
    realized = sum((t.pnl for t in result.trades), Decimal(0))
    assert abs((result.initial_cash + realized) - result.final_equity) < Decimal("0.000001")


@_SETTINGS
@given(scn=scenario())
def test_determinism(scn) -> None:  # type: ignore[no-untyped-def]
    """Identical inputs must produce a byte-identical result — the precondition for
    every reproducibility claim the product makes."""
    a, b = _run(scn), _run(scn)
    assert [p.equity for p in a.equity_curve] == [p.equity for p in b.equity_curve]
    assert [(t.entry_ts, t.exit_ts, t.qty, t.pnl) for t in a.trades] == [
        (t.entry_ts, t.exit_ts, t.qty, t.pnl) for t in b.trades
    ]


@_SETTINGS
@given(scn=scenario())
def test_trades_are_well_formed(scn) -> None:  # type: ignore[no-untyped-def]
    """No zero/negative size, no exit before entry, no negative commission."""
    result = _run(scn)
    for t in result.trades:
        assert t.qty > 0
        assert t.entry_ts <= t.exit_ts
        assert t.entry_price > 0 and t.exit_price > 0
        assert t.commission >= 0
        assert t.bars_held >= 0


@_SETTINGS
@given(scn=scenario())
def test_fills_lie_inside_the_bar_or_are_explained_by_slippage(scn) -> None:  # type: ignore[no-untyped-def]
    """A fill must be a price the market actually printed, adjusted only by the
    modelled slippage — never an invented level outside the bar's range."""
    _spec, bars, config = scn
    result = _run(scn)
    by_ts = {b.ts: b for b in bars}
    slip = Decimal(str(config.slippage_bps)) / Decimal(10000)
    tol = Decimal("1.0000001")
    for t in result.trades:
        entry_bar = by_ts[t.entry_ts]
        raw_entry = t.entry_price / (Decimal(1) + slip)
        assert entry_bar.low / tol <= raw_entry <= entry_bar.high * tol
        exit_bar = by_ts[t.exit_ts]
        raw_exit = t.exit_price / (Decimal(1) - slip) if slip else t.exit_price
        assert exit_bar.low / tol <= raw_exit <= exit_bar.high * tol


@_SETTINGS
@given(scn=scenario())
def test_position_never_exceeds_the_configured_cap(scn) -> None:  # type: ignore[no-untyped-def]
    """max_position_pct is ENFORCED, not merely recorded.

    The cap is a fraction of equity AT THE MOMENT OF ENTRY, not of the starting
    balance — a strategy that has doubled may hold twice the notional at the same
    percentage. Because the engine is always flat immediately before an entry, the
    mark-to-market at the previous bar's close IS the cash it sizes against, which
    is what makes this checkable from the artifact alone.
    """
    spec, _bars, config = scn
    result = _run(scn)
    cap = Decimal(str(spec.risk.max_position_pct))
    index_of = {p.ts: i for i, p in enumerate(result.equity_curve)}
    for t in result.trades:
        i = index_of[t.entry_ts]
        equity_at_entry = result.equity_curve[i - 1].equity if i > 0 else config.initial_cash
        assert t.qty * t.entry_price <= equity_at_entry * cap * Decimal("1.000001")


@_SETTINGS
@given(scn=scenario())
def test_trade_commission_is_the_configured_rate_on_both_legs(scn) -> None:  # type: ignore[no-untyped-def]
    """Every trade reports the full round-trip commission at the configured rate.

    Recording only the exit leg (which the engine used to do) leaves the account
    balance correct but halves the number any report, export or metric derives from
    the trade — the cost model would look half as expensive as it actually is.
    """
    _spec, _bars, config = scn
    result = _run(scn)
    rate = Decimal(str(config.commission_bps)) / Decimal(10000)
    for t in result.trades:
        expected = (t.qty * t.entry_price * rate) + (t.qty * t.exit_price * rate)
        assert abs(t.commission - expected) < Decimal("0.0000001")
    if config.commission_bps == 0:
        assert result.total_commission == Decimal(0)
    assert result.total_commission >= 0


@_SETTINGS
@given(scn=scenario())
def test_higher_costs_never_produce_a_cheaper_round_trip(scn) -> None:  # type: ignore[no-untyped-def]
    """Per unit of notional traded, dearer settings must cost more.

    Note this is deliberately NOT "higher costs always reduce final equity" — that
    is false, and Hypothesis found the counterexample: with a consecutive-loss kill
    switch, higher costs can turn the first trade into a loss, halt the strategy
    earlier, and thereby PRESERVE capital that the cheaper run went on to lose. The
    risk controls interact with the cost model, so the honest invariant is about the
    cost of trading, not about the outcome of the strategy.
    """
    spec, bars, _config = scn
    cheap = engine.run(spec, bars, ExecutionConfig(commission_bps=1.0, slippage_bps=0.0))
    dear = engine.run(spec, bars, ExecutionConfig(commission_bps=50.0, slippage_bps=0.0))

    def cost_per_notional(result) -> Decimal | None:  # type: ignore[no-untyped-def]
        notional = sum((t.qty * t.entry_price for t in result.trades), Decimal(0))
        if notional == 0:
            return None
        return result.total_commission / notional

    cheap_rate, dear_rate = cost_per_notional(cheap), cost_per_notional(dear)
    if cheap_rate is not None and dear_rate is not None:
        assert dear_rate > cheap_rate


@_SETTINGS
@given(scn=scenario())
def test_consecutive_loss_halt_stops_all_later_entries(scn) -> None:  # type: ignore[no-untyped-def]
    """Once the kill-switch fires, no NEW position may be opened.

    A risk control that only records an event is not a risk control.
    """
    spec, _bars, _config = scn
    if spec.risk.max_consecutive_losses is None:
        return
    result = _run(scn)
    halt = next((e for e in result.risk_events if e.kind == "max_consecutive_losses"), None)
    if halt is None:
        return
    # The trade that triggered the halt exits exactly at the halt timestamp; any
    # LATER entry would mean the switch was ignored.
    for t in result.trades:
        assert t.entry_ts <= halt.ts


@_SETTINGS
@given(scn=scenario())
def test_equity_curve_is_aligned_with_the_bars(scn) -> None:  # type: ignore[no-untyped-def]
    """One equity point per bar, in order, with matching timestamps."""
    _spec, bars, _config = scn
    result = _run(scn)
    assert len(result.equity_curve) == len(bars)
    assert [p.ts for p in result.equity_curve] == [b.ts for b in bars]
    assert result.bars == len(bars)
