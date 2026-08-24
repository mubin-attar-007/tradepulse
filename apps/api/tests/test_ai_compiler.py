"""The NL→strategy compiler: extraction, compilation, and semantic verification.

Hermetic — no model, no network, no database. The deterministic extractor is the
reference the whole AI layer is judged against, so it needs to be pinned harder
than anything that calls it.
"""

from __future__ import annotations

import pytest

from app.modules.ai import compiler
from app.modules.ai.ir import (
    CompileError,
    ExitIntent,
    Rule,
    StrategyIntent,
    Term,
    compile_intent,
)

EMA_CROSS = (
    "Buy BTC/USD on the 1h chart when the 20-period EMA crosses above the 50-period EMA, "
    "and exit when it crosses back below. Use a 2% stop loss and risk 1% of equity per trade."
)


# --- extraction --------------------------------------------------------------


def test_extracts_the_canonical_crossover_request() -> None:
    intent = compiler.extract(EMA_CROSS).intent
    assert intent.symbol == "BTC/USD"
    assert intent.timeframe == "1h"
    assert [r.signature() for r in intent.entry] == ["EMA(period=20) crosses_above EMA(period=50)"]
    assert [r.signature() for r in intent.exit.rules] == [
        "EMA(period=20) crosses_below EMA(period=50)"
    ]
    assert intent.exit.stop_loss_pct == pytest.approx(0.02)
    assert intent.sizing.method == "risk_per_trade"
    assert intent.sizing.value == pytest.approx(0.01)
    assert intent.unsupported == []


def test_fast_and_slow_are_assigned_by_period_not_mention_order() -> None:
    """ "...the 50 EMA is crossed by the 20 EMA" must not invert the legs."""
    intent = compiler.extract(
        "Enter when the 50 EMA is crossed above by the 20 EMA on BTC hourly"
    ).intent
    if intent.entry:
        rule = intent.entry[0]
        assert rule.left.params["period"] == 20
        assert rule.right.params["period"] == 50


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("on the 5-minute chart", "5m"),
        ("using 15m bars", "15m"),
        ("hourly", "1h"),
        ("on the 4h chart", "4h"),
        ("daily bars", "1d"),
        ("1-minute candles", "1m"),
    ],
)
def test_timeframe_vocabulary(phrase: str, expected: str) -> None:
    intent = compiler.extract(f"Buy AAPL when RSI(14) is below 30 {phrase}").intent
    assert intent.timeframe == expected


def test_percentages_are_read_as_fractions() -> None:
    intent = compiler.extract(
        "Buy SPY daily when RSI(14) drops below 30, stop loss of 2.5%, take profit at 7%, "
        "with a 3% trailing stop"
    ).intent
    assert intent.exit.stop_loss_pct == pytest.approx(0.025)
    assert intent.exit.take_profit_pct == pytest.approx(0.07)
    assert intent.exit.trailing_stop_pct == pytest.approx(0.03)


def test_an_unknown_ticker_is_not_guessed() -> None:
    """Inventing an instrument from a capitalised word produces confident nonsense.

    Leaving it null makes the compiler state its default explicitly instead.
    """
    intent = compiler.extract("Buy ZZZZ when the 10 EMA crosses above the 30 EMA").intent
    assert intent.symbol is None


@pytest.mark.parametrize(
    ("request_text", "expected_fragment"),
    [
        ("Build me a guaranteed profitable strategy", "guaranteed"),
        ("Trade options on SPY with a call spread", "options"),
        ("Use 10x leverage on BTC", "leverage"),
        ("Go short when the trend turns down", "short entries"),
        ("Use insider information about earnings", "insider"),
        ("Actually buy the shares with real money", "real-money"),
        ("Predict the price tomorrow and buy before it moves", "future data"),
        ("Trade a portfolio of every stock in the S&P", "multi-instrument"),
    ],
)
def test_unsupported_requests_are_detected(request_text: str, expected_fragment: str) -> None:
    intent = compiler.extract(request_text).intent
    assert any(expected_fragment in reason for reason in intent.unsupported), intent.unsupported


@pytest.mark.parametrize(
    ("request_text", "expected_fragment"),
    [
        ("Buy on strong momentum", "strong momentum"),
        ("Enter on high volume", "high volume"),
        ("A low risk strategy for BTC", "low risk"),
        ("Use a tight stop", "tight stop"),
        ("Trade large-cap stocks", "universe rule"),
        ("A short-term strategy", "short/long-term"),
    ],
)
def test_ambiguous_phrasing_is_flagged_rather_than_guessed(
    request_text: str, expected_fragment: str
) -> None:
    intent = compiler.extract(request_text).intent
    assert any(expected_fragment in reason for reason in intent.ambiguities), intent.ambiguities


def test_a_fully_specified_request_raises_no_ambiguity() -> None:
    """A checker that cries wolf gets ignored, so precision matters more than recall."""
    assert compiler.extract(EMA_CROSS).intent.ambiguities == []


# --- compilation -------------------------------------------------------------


def test_compiles_to_a_valid_spec_with_readable_indicator_ids() -> None:
    intent = compiler.extract(EMA_CROSS).intent
    spec, applied = compile_intent(intent)
    assert [i.id for i in spec.indicators] == ["ema_20", "ema_50"]
    assert spec.universe == ["BTC/USD"]
    assert spec.timeframe == "1h"
    assert spec.exit.stop_loss_pct == pytest.approx(0.02)
    assert applied == []
    assert len(spec.spec_hash()) == 64


def test_the_same_indicator_is_allocated_once() -> None:
    """Two rules naming EMA(20) must share one declaration, not duplicate it."""
    intent = StrategyIntent(
        entry=[
            Rule(
                left=Term(kind="price", field="close"),
                op="above",
                right=Term(kind="indicator", indicator="EMA", params={"period": 20}),
            )
        ],
        exit=ExitIntent(
            rules=[
                Rule(
                    left=Term(kind="price", field="close"),
                    op="below",
                    right=Term(kind="indicator", indicator="EMA", params={"period": 20}),
                )
            ],
            stop_loss_pct=0.05,
        ),
    )
    spec, _ = compile_intent(intent)
    assert len(spec.indicators) == 1


def test_defaults_are_applied_and_reported_not_hidden() -> None:
    """A silently-applied default changes the strategy the user thinks they wrote."""
    intent = compiler.extract("Buy when the 10 EMA crosses above the 30 EMA").intent
    spec, applied = compile_intent(intent)
    assert spec.exit.stop_loss_pct is not None
    joined = " ".join(applied)
    assert "instrument defaulted" in joined
    assert "timeframe defaulted" in joined
    assert "protective stop" in joined


def test_risk_per_trade_without_a_stop_is_downgraded_and_disclosed() -> None:
    """The DSL rejects risk-per-trade with no stop; falling back silently would
    change the risk profile without telling anyone."""
    intent = StrategyIntent(
        symbol="BTC/USD",
        timeframe="1h",
        entry=[
            Rule(
                left=Term(kind="price", field="close"),
                op="above",
                right=Term(kind="indicator", indicator="SMA", params={"period": 20}),
            )
        ],
        exit=ExitIntent(take_profit_pct=0.05),
    )
    intent.sizing.method = "risk_per_trade"
    intent.sizing.value = 0.01
    spec, applied = compile_intent(intent)
    assert spec.sizing.method == "percent_equity"
    assert any("risk-per-trade" in note for note in applied)


def test_an_entryless_intent_is_refused() -> None:
    with pytest.raises(CompileError):
        compile_intent(StrategyIntent())


def test_compiled_specs_inherit_every_dsl_capability_guard() -> None:
    """Model output goes through exactly the same validator as hand-authored input."""
    intent = StrategyIntent(
        entry=[
            Rule(
                left=Term(kind="price", field="close"),
                op="above",
                # Period far outside the catalog's allowed range.
                right=Term(kind="indicator", indicator="SMA", params={"period": 99999}),
            )
        ],
        exit=ExitIntent(stop_loss_pct=0.05),
    )
    with pytest.raises(CompileError):
        compile_intent(intent)


# --- semantic verification ---------------------------------------------------


def test_verification_passes_when_the_strategy_matches_the_request() -> None:
    assert compiler.verify(EMA_CROSS, compiler.extract(EMA_CROSS).intent) == []


def test_swapping_the_indicator_type_is_caught() -> None:
    """EMA -> SMA is schema-valid and completely wrong. This is the whole point."""
    wrong = compiler.extract(
        "Buy BTC/USD on the 1h chart when the 20-period SMA crosses above the 50-period SMA"
    ).intent
    issues = compiler.verify(EMA_CROSS, wrong)
    assert any(i.constraint.kind == "indicator" for i in issues)


def test_changing_a_period_is_caught() -> None:
    wrong = compiler.extract(
        "Buy BTC/USD on the 1h chart when the 10-period EMA crosses above the 30-period EMA"
    ).intent
    issues = compiler.verify(EMA_CROSS, wrong)
    assert any(i.constraint.kind == "period" for i in issues)


def test_inverting_the_operator_is_caught() -> None:
    wrong = compiler.extract(
        "Buy BTC/USD on the 1h chart when the 20-period EMA crosses below the 50-period EMA"
    ).intent
    issues = compiler.verify(EMA_CROSS, wrong)
    assert any(i.constraint.kind == "operator" for i in issues)


def test_changing_the_stop_is_caught() -> None:
    produced = compiler.extract(EMA_CROSS).intent
    produced.exit.stop_loss_pct = 0.10
    issues = compiler.verify(EMA_CROSS, produced)
    assert any(i.constraint.kind == "stop" for i in issues)
    assert "2.00%" in issues[0].problem or "10.00%" in issues[0].problem


def test_changing_the_instrument_or_timeframe_is_caught() -> None:
    produced = compiler.extract(EMA_CROSS).intent
    produced.symbol = "ETH/USD"
    produced.timeframe = "1d"
    kinds = {i.constraint.kind for i in compiler.verify(EMA_CROSS, produced)}
    assert {"symbol", "timeframe"} <= kinds


def test_verification_reports_the_evidence_it_used() -> None:
    """A semantic failure has to be checkable by a human, so it cites the phrase."""
    wrong = compiler.extract("Buy BTC/USD hourly when the 20 SMA crosses above the 50 SMA").intent
    issues = compiler.verify(EMA_CROSS, wrong)
    assert issues
    for issue in issues:
        payload = issue.as_dict()
        assert payload["evidence"]
        assert payload["expected"]
        assert payload["problem"]


def test_a_wrong_operand_inside_a_correct_looking_rule_is_caught() -> None:
    """The failure a per-constraint check cannot see.

    A local model produced a correct entry (EMA 20 crosses above EMA 50) and an exit
    of "EMA 20 crosses below 0". Every individual constraint was satisfied SOMEWHERE
    in the strategy — both EMAs appear, both periods appear, both operators appear —
    so nothing was flagged while the exit rule was nonsense. Operand-set comparison
    per rule is what catches it.
    """
    produced = compiler.extract(EMA_CROSS).intent
    produced.exit.rules = [
        Rule(
            left=Term(kind="indicator", indicator="EMA", params={"period": 20}),
            op="crosses_below",
            right=Term(kind="const", value=0.0),
        )
    ]
    issues = compiler.verify(EMA_CROSS, produced)
    assert any(i.constraint.kind == "rule_operands" for i in issues)
    assert any("exit rule compares" in i.problem for i in issues)


def test_operand_comparison_is_order_insensitive() -> None:
    """ "A crosses below B" and "B crosses above A" describe the same event.

    Failing a model for choosing the other form would be a false positive, and the
    operator direction is already covered by the separate operator constraints.
    """
    produced = compiler.extract(EMA_CROSS).intent
    entry = produced.entry[0]
    produced.entry = [Rule(left=entry.right, op="crosses_below", right=entry.left)]
    operand_issues = [
        i for i in compiler.verify(EMA_CROSS, produced) if i.constraint.kind == "rule_operands"
    ]
    assert [i for i in operand_issues if i.constraint.detail.startswith("entry:")] == []
