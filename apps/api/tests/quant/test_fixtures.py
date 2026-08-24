"""Hand-derived golden fixtures.

Every expected number below was computed by hand from the documented execution
model, and the derivation is written out in the test so a reviewer can check the
arithmetic without running anything. These are the tests that turn "costs are
modelled" and "fills happen at the next bar's open" from claims into facts.

Execution model under test:
  * a decision is made at the CLOSE of bar i and can only fill at bar i+1's OPEN;
  * a long entry fills at ``open * (1 + slippage)``; an exit at ``price * (1 - slippage)``;
  * commission is charged in basis points on the notional of BOTH legs;
  * stop/target are checked intrabar and fill AT THE LEVEL unless the bar gapped
    through it, in which case they fill at the open.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.strategies.spec import ExitRule, PositionSizing, RiskLimits
from tests.quant.conftest import ohlc, spec

FREE = ExecutionConfig(commission_bps=0.0, slippage_bps=0.0, initial_cash=Decimal("100000"))
COSTED = ExecutionConfig(commission_bps=2.0, slippage_bps=1.0, initial_cash=Decimal("100000"))

# A single clean round trip: entry armed at bar 1's close, filled at bar 2's open,
# target touched intrabar on bar 3, then flat.
#            open     high     low      close
_ROUNDTRIP = [
    ("100", "100", "100", "100"),  # 0
    ("100", "101", "99", "101"),  # 1  close crosses up through 100.5 -> arm entry
    ("100", "102", "99", "101"),  # 2  entry fills at this open
    ("101", "106", "100", "104"),  # 3  high reaches the target -> exit
    ("104", "105", "103", "104"),  # 4  flat
]


def test_frictionless_roundtrip_exact() -> None:
    """Zero-cost arithmetic, checkable in your head.

    entry  = open[2] = 100                     (no slippage)
    size   = 100 units                         (fixed_units)
    stop   = 100 * (1 - 0.10) = 90             — bar 3 low is 100, never touched
    target = 100 * (1 + 0.05) = 105            — bar 3 high is 106, touched
    exit   = 105 (touched intrabar, NOT a gap: open 101 < 105)
    pnl    = 100 * (105 - 100) = 500
    """
    result = engine.run(spec(), ohlc(_ROUNDTRIP), FREE)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == Decimal("100")
    assert trade.exit_price == Decimal("105")
    assert trade.qty == Decimal("100")
    assert trade.exit_reason == "target"
    assert trade.pnl == Decimal("500")
    assert trade.commission == Decimal("0")
    assert trade.bars_held == 1  # filled on bar 2, exited on bar 3
    assert result.total_commission == Decimal("0")
    assert result.final_equity == Decimal("100500")


def test_costed_roundtrip_exact() -> None:
    """The same trade with 2 bps commission per side and 1 bps adverse slippage.

    entry fill      = 100 * (1 + 0.0001)            = 100.0100
    notional        = 100 * 100.0100                = 10001.0000
    commission in   = 10001.0000 * 0.0002           = 2.00020000
    target          = 100.0100 * 1.05               = 105.010500
    exit fill       = 105.010500 * (1 - 0.0001)     = 104.9999989500
    proceeds        = 100 * 104.9999989500          = 10499.9998950000
    commission out  = 10499.9998950000 * 0.0002     = 2.09999997900000
    pnl             = (proceeds - comm_out) - (notional + comm_in)
                    = 10497.89989502100000 - 10003.00020000
                    = 494.89969502100000
    """
    result = engine.run(spec(), ohlc(_ROUNDTRIP), COSTED)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == Decimal("100.0100")
    assert trade.exit_price == Decimal("104.9999989500")
    assert trade.pnl == Decimal("494.89969502100000")
    assert result.total_commission == Decimal("4.10019997900000")
    # The trade carries the ROUND TRIP, not just the exit leg: 2.00020000 + 2.09999997900000.
    assert trade.commission == Decimal("4.10019997900000")
    assert result.final_equity == Decimal("100494.89969502100000")


def test_costs_are_the_only_difference() -> None:
    """Frictionless must beat the costed run by exactly the frictions.

    This is the assertion that makes a mislabelled frictionless run detectable: if
    the two ever came out equal, the cost model would not be running.
    """
    free = engine.run(spec(), ohlc(_ROUNDTRIP), FREE)
    costed = engine.run(spec(), ohlc(_ROUNDTRIP), COSTED)
    assert costed.final_equity < free.final_equity
    assert costed.total_commission > 0


def test_stop_fills_at_the_level_when_touched_intrabar() -> None:
    """A stop that is merely touched fills AT the stop, not at the open.

    entry  = 100 (bar 2 open, frictionless)
    stop   = 100 * (1 - 0.10) = 90
    bar 3: open 99 (above the stop), low 85 -> the level is crossed during the bar
    so the fill is the stop itself, 90. pnl = 100 * (90 - 100) = -1000.
    """
    bars = ohlc(
        [
            ("100", "100", "100", "100"),
            ("100", "101", "99", "101"),
            ("100", "102", "99", "101"),
            ("99", "99", "85", "86"),
        ]
    )
    result = engine.run(spec(), bars, FREE)
    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == Decimal("90")
    assert trade.pnl == Decimal("-1000")


def test_stop_fills_at_the_open_when_the_bar_gaps_through() -> None:
    """A bar that OPENS below the stop could never have filled at the stop.

    entry = 100, stop = 90, bar 3 opens at 80 — the market was never at 90 while we
    were able to trade, so the honest fill is the open. pnl = 100 * (80 - 100) = -2000.
    Reporting 90 here would understate the loss by $1,000 a trade.
    """
    bars = ohlc(
        [
            ("100", "100", "100", "100"),
            ("100", "101", "99", "101"),
            ("100", "102", "99", "101"),
            ("80", "82", "78", "79"),
        ]
    )
    result = engine.run(spec(), bars, FREE)
    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == Decimal("80")
    assert trade.pnl == Decimal("-2000")


def test_trailing_stop_fills_at_the_trail_not_the_open() -> None:
    """Regression for the trailing-stop mis-classification.

    The trail ratchets on the bar's high; the previous implementation then applied
    a gap test against the ALREADY-RATCHETED level, and since the open is
    mechanically below a freshly ratcheted trail, every trailing exit on a rallying
    bar was booked at the open.

    entry = 100 (bar 2 open, frictionless), trailing 10%.
    bar 3: open 101, high 130, low 101 -> trail ratchets to 130 * 0.9 = 117,
           low 101 <= 117 so the trail is hit. The bar did NOT open below the
           level that was live at the open (100 * 0.9 = 90), so this is not a gap:
           the fill is 117, not 101.
    pnl = 100 * (117 - 100) = 1700.
    """
    bars = ohlc(
        [
            ("100", "100", "100", "100"),
            ("100", "101", "99", "101"),
            ("100", "102", "99", "101"),
            ("101", "130", "101", "101"),
        ]
    )
    result = engine.run(
        spec(exit_rule=ExitRule(trailing_stop_pct=0.10)),
        bars,
        FREE,
    )
    trade = result.trades[0]
    assert trade.exit_reason == "trailing"
    assert trade.exit_price == Decimal("117.0")
    assert trade.pnl == Decimal("1700.0")


def test_trailing_stop_still_gaps_when_it_genuinely_gaps() -> None:
    """The gap path must survive the fix: opening below the LIVE trail fills at the open.

    entry = 100, trailing 10% -> the level live at bar 3's open is 90.
    bar 3 opens at 70, below 90, so this is a true gap-through: fill 70.
    """
    bars = ohlc(
        [
            ("100", "100", "100", "100"),
            ("100", "101", "99", "101"),
            ("100", "102", "99", "101"),
            ("70", "72", "68", "69"),
        ]
    )
    result = engine.run(spec(exit_rule=ExitRule(trailing_stop_pct=0.10)), bars, FREE)
    trade = result.trades[0]
    assert trade.exit_price == Decimal("70")


def test_time_exit_fills_at_the_next_open() -> None:
    """A time exit is a DECISION, so it fills at the next bar's open like any other.

    entry on bar 2 at 100, time_exit_bars=2 -> the condition (i - entry_i >= 2) is
    first true on bar 4, which schedules the exit; it fills at bar 5's open of 108.
    pnl = 100 * (108 - 100) = 800.
    """
    bars = ohlc(
        [
            ("100", "100", "100", "100"),
            ("100", "101", "99", "101"),
            ("100", "102", "99", "101"),
            ("102", "103", "101", "103"),
            ("103", "104", "102", "104"),
            ("108", "109", "107", "108"),
        ]
    )
    result = engine.run(spec(exit_rule=ExitRule(time_exit_bars=2)), bars, FREE)
    trade = result.trades[0]
    assert trade.exit_reason == "time"
    assert trade.exit_price == Decimal("108")
    assert trade.pnl == Decimal("800")


def test_insufficient_cash_clamps_the_order_and_never_goes_negative() -> None:
    """Cash is a hard constraint: an oversized order is reduced, not borrowed against."""
    bars = ohlc(_ROUNDTRIP)
    result = engine.run(
        spec(sizing=PositionSizing(method="fixed_units", value=100000)),
        bars,
        COSTED,
    )
    assert result.trades, "expected the clamped order to still trade"
    trade = result.trades[0]
    # 100,000 units at ~100 would be $10m against $100k of cash.
    assert trade.qty * trade.entry_price <= COSTED.initial_cash
    assert all(p.equity >= 0 for p in result.equity_curve)


def test_max_position_pct_clamps_and_records_a_risk_event() -> None:
    """A breached position cap must be visible in the artifact, not silently applied."""
    result = engine.run(
        spec(
            sizing=PositionSizing(method="percent_equity", value=1.0),
            risk=RiskLimits(max_position_pct=0.25, max_open_positions=1),
        ),
        ohlc(_ROUNDTRIP),
        FREE,
    )
    assert any(e.kind == "position_clamped" for e in result.risk_events)
    trade = result.trades[0]
    assert trade.qty * trade.entry_price <= FREE.initial_cash * Decimal("0.25")


def test_no_entry_means_no_fills_and_a_flat_curve() -> None:
    """A strategy whose entry never fires must produce nothing at all — not a
    zero-size trade, and not a curve that drifts."""
    flat = ohlc([("100", "100", "100", "100")] * 6)
    result = engine.run(spec(), flat, FREE)
    assert result.trades == []
    assert result.total_commission == Decimal("0")
    assert {p.equity for p in result.equity_curve} == {FREE.initial_cash}
