"""Deterministic intent extraction and semantic verification.

Two jobs, one body of rules:

1. **Extraction.** Parse a natural-language request into the strategy IR using
   explicit patterns. This is not a fallback for when the model is unavailable — it
   is the reference. It runs on every request, before and independently of any
   model call.

2. **Verification.** Compare what the user asked for against what the model
   produced, in the IR's vocabulary. This is the check the audit found missing: the
   v1 pipeline validated that model output was schema-VALID, which says nothing
   about whether it was the strategy the user described. A model that answers a
   request for a 20/50 EMA cross with a 10/30 SMA cross produced perfectly valid
   JSON and the wrong strategy, and nothing in the system noticed.

Deliberate design choice: extraction is conservative. It only claims a constraint
it can point at in the text. A constraint it did not find is simply absent — so the
checker never fails a model for disagreeing with something the extractor imagined.
Precision matters far more than recall here, because a false semantic failure
teaches users to ignore the checker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.ai.ir import ExitIntent, RiskIntent, Rule, SizingIntent, StrategyIntent, Term
from app.modules.strategies.spec import Timeframe

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #

_TIMEFRAME_PATTERNS: list[tuple[str, Timeframe]] = [
    (r"\b1\s*-?\s*minute\b|\b1m\b|\bone[- ]minute\b", "1m"),
    (r"\b5\s*-?\s*minute\b|\b5m\b|\bfive[- ]minute\b", "5m"),
    (r"\b15\s*-?\s*minute\b|\b15m\b|\bfifteen[- ]minute\b", "15m"),
    (r"\b1\s*-?\s*hour\b|\bhourly\b|\b1h\b|\b60\s*-?\s*minute\b", "1h"),
    (r"\b4\s*-?\s*hour\b|\b4h\b|\bfour[- ]hour\b", "4h"),
    (r"\bdaily\b|\b1d\b|\bday\s+chart\b|\bdaily\s+bars?\b", "1d"),
]

# Canonical symbols the platform seeds. A bare ticker is only accepted from this
# list: guessing that an unknown capitalised word is a ticker produces confident
# nonsense, and an unrecognised instrument is a far better answer.
_KNOWN_SYMBOLS = {
    "BTC": "BTC/USD",
    "BITCOIN": "BTC/USD",
    "BTC/USD": "BTC/USD",
    "BTCUSD": "BTC/USD",
    "ETH": "ETH/USD",
    "ETHEREUM": "ETH/USD",
    "ETH/USD": "ETH/USD",
    "ETHUSD": "ETH/USD",
    "AAPL": "AAPL",
    "APPLE": "AAPL",
    "MSFT": "MSFT",
    "MICROSOFT": "MSFT",
    "SPY": "SPY",
}

_INDICATOR_WORDS: list[tuple[str, str]] = [
    (r"\bexponential\s+moving\s+average\b|\bema\b", "EMA"),
    # The bare "moving average" alternative must not fire inside "exponential moving
    # average", or a single EMA phrase yields both an EMA and an SMA constraint and
    # the semantic checker then reports a contradiction the user never wrote.
    (r"\bsimple\s+moving\s+average\b|\bsma\b|(?<!exponential\s)\bmoving\s+average\b", "SMA"),
    (r"\brelative\s+strength\s+index\b|\brsi\b", "RSI"),
    (r"\baverage\s+true\s+range\b|\batr\b", "ATR"),
    (r"\bbollinger\b|\bbbands?\b", "BBANDS"),
    (r"\bmacd\b", "MACD"),
    (r"\bvwap\b|\bvolume[- ]weighted\b", "VWAP"),
    (r"\bvolume\s+average\b|\baverage\s+volume\b|\bvol[_ ]sma\b", "VOL_SMA"),
]

# Requests the platform will not serve, and the reason. Detected up front so the
# answer is an explanation rather than a plausible-looking strategy.
_UNSUPPORTED_PATTERNS: list[tuple[str, str]] = [
    (
        r"\bguarantee\w*\b|\brisk[- ]free\b|\bno\s+risk\b|\bcan'?t\s+lose\b",
        "guaranteed or risk-free performance: no backtest can establish this",
    ),
    (
        r"\binsider\b|\bnon[- ]public\b|\bmaterial\s+non[- ]public\b",
        "insider or non-public information",
    ),
    (
        r"\boption[s]?\b|\bcall\s+spread\b|\bput\s+spread\b|\bstraddle\b|\biron\s+condor\b",
        "options strategies: the engine models spot instruments only",
    ),
    (
        r"\bfutures?\s+contract\b|\bperpetual\s+swap\b|\bfunding\s+rate\b",
        "derivatives: the engine models spot instruments only",
    ),
    (
        r"\b(\d+)\s*x\s+leverage\b|\bleverage[d]?\b|\bmargin\s+trad\w+\b",
        "leverage: the engine is unlevered and caps position size at available cash",
    ),
    (
        r"\bshort\s+(?:sell|selling|the\s+market|position)\b|\bgo\s+short\b",
        "short entries: engine 0.1.0 is long-only",
    ),
    (
        r"\breal\s+money\b|\blive\s+trade|\bactually\s+(?:buy|sell|trade)\b|\bexecute\s+for\s+real\b",
        "real-money execution: the platform is simulation-only and the live path is gated off",
    ),
    (
        r"\bfuture\s+price\b|\btomorrow'?s\s+(?:price|close)\b|\bpredict\s+the\s+(?:price|market)\b",
        "using future data: decisions are made only on closed bars",
    ),
    (
        r"\bmultiple\s+(?:symbols|instruments|assets)\b|\bportfolio\s+of\b|\ball\s+s&p\b|\bevery\s+stock\b",
        "multi-instrument portfolios: the engine backtests one instrument at a time",
    ),
]

# Phrases with no defensible default. Asking is better than guessing, because a
# guess here silently changes the strategy the user believes they authored.
_AMBIGUOUS_PATTERNS: list[tuple[str, str]] = [
    (
        r"\bshort[- ]term\b|\blong[- ]term\b|\bmedium[- ]term\b",
        "'short/long-term' does not map to a timeframe on its own",
    ),
    (
        r"\bhigh\s+volume\b|\bheavy\s+volume\b|\bunusual\s+volume\b",
        "'high volume' needs a threshold (e.g. 1.5x the 20-period average)",
    ),
    (
        r"\blow\s+risk\b|\bsafe\b|\bconservative\b",
        "'low risk' needs concrete limits (stop distance, position cap, max drawdown)",
    ),
    (
        r"\bstrong\s+momentum\b|\bstrong\s+trend\b|\btrending\s+up\b",
        "'strong momentum' needs an indicator and a threshold",
    ),
    (r"\btight\s+stop\b|\bclose\s+stop\b", "'tight stop' needs a percentage"),
    (r"\brecent\b|\blately\b|\bcurrently\b", "'recent' needs an explicit date range"),
    (
        r"\bbeat\s+the\s+market\b|\boutperform\b",
        "'beat the market' needs a named benchmark and period",
    ),
    (
        r"\blarge[- ]cap\b|\bblue[- ]chip\b|\bpenny\s+stocks?\b",
        "a universe rule is not supported; name one instrument",
    ),
    (
        r"\bprofitable\b|\bmakes?\s+money\b|\bbest\s+strategy\b",
        "'profitable' is an outcome, not a rule; the platform tests rules rather "
        "than promising outcomes",
    ),
]


@dataclass(frozen=True, slots=True)
class Constraint:
    """One thing the user's text unambiguously asked for."""

    kind: str  # indicator | period | operator | timeframe | symbol | stop | target | trailing
    detail: str
    evidence: str  # the exact phrase it came from


@dataclass
class Extraction:
    intent: StrategyIntent
    constraints: list[Constraint] = field(default_factory=list)


def _find_timeframe(text: str) -> tuple[Timeframe | None, str]:
    for pattern, tf in _TIMEFRAME_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return tf, match.group(0)
    return None, ""


def _find_symbol(text: str) -> tuple[str | None, str]:
    # Longest first so 'BTC/USD' wins over a bare 'BTC'.
    for token in sorted(_KNOWN_SYMBOLS, key=len, reverse=True):
        pattern = re.escape(token).replace("/", r"\s*/\s*")
        match = re.search(rf"\b{pattern}\b", text, re.I)
        if match:
            return _KNOWN_SYMBOLS[token], match.group(0)
    return None, ""


def _percent(text: str, *patterns: str) -> tuple[float | None, str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            raw = float(match.group("pct"))
            return raw / 100.0, match.group(0)
    return None, ""


def _indicator_terms(text: str) -> list[tuple[str, int | None, str]]:
    """Every ``(indicator, period, evidence)`` mentioned, in order of appearance.

    Handles the shapes people actually write: "20 EMA", "EMA(20)", "EMA 20",
    "20-period exponential moving average", "RSI(14)".
    """
    found: list[tuple[int, str, int | None, str]] = []
    for pattern, name in _INDICATOR_WORDS:
        for match in re.finditer(pattern, text, re.I):
            start, end = match.span()
            window_before = text[max(0, start - 24) : start]
            window_after = text[end : end + 18]
            period: int | None = None
            after = re.match(r"\s*\(?\s*(\d{1,4})", window_after)
            before = re.search(r"(\d{1,4})\s*(?:-?\s*(?:period|day|bar)s?)?\s*$", window_before)
            if after:
                period = int(after.group(1))
            elif before:
                period = int(before.group(1))
            found.append((start, name, period, match.group(0)))
    found.sort(key=lambda item: item[0])
    # Collapse exact duplicates (the same indicator+period mentioned twice) while
    # preserving order and keeping genuinely distinct periods (20 EMA and 50 EMA).
    seen: set[tuple[str, int | None]] = set()
    out: list[tuple[str, int | None, str]] = []
    for _pos, name, period, evidence in found:
        key = (name, period)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, period, evidence))
    return out


def _term_for(name: str, period: int | None) -> Term | None:
    if name == "VWAP":
        return Term(kind="indicator", indicator="VWAP", params={})
    if name == "BBANDS":
        return Term(
            kind="indicator",
            indicator="BBANDS",
            params={"period": float(period or 20), "std": 2.0},
            output="lower",
        )
    if name == "MACD":
        return Term(
            kind="indicator",
            indicator="MACD",
            params={"fast": 12.0, "slow": 26.0, "signal": 9.0},
            output="macd",
        )
    if period is None:
        return None
    return Term(kind="indicator", indicator=name, params={"period": float(period)})


# An intervening adverb is extremely common in how people actually write this
# ("crosses back below", "crosses back above"), and missing it silently dropped the
# exit leg of the single most common strategy request.
_ADVERB = r"(?:\s+(?:back|down|up|again))?"
_CROSS_ABOVE = rf"cross(?:es|ing|ed)?{_ADVERB}\s+(?:above|over|up\s+through)"
_CROSS_BELOW = rf"cross(?:es|ing|ed)?{_ADVERB}\s+(?:below|under|down\s+through)"


def extract(request: str) -> Extraction:
    """Parse a request into the IR plus the constraints it unambiguously states."""
    text = " ".join(request.split())
    constraints: list[Constraint] = []

    timeframe, tf_evidence = _find_timeframe(text)
    if timeframe:
        constraints.append(Constraint("timeframe", timeframe, tf_evidence))
    symbol, sym_evidence = _find_symbol(text)
    if symbol:
        constraints.append(Constraint("symbol", symbol, sym_evidence))

    indicators = _indicator_terms(text)
    for name, period, evidence in indicators:
        constraints.append(Constraint("indicator", name, evidence))
        if period is not None:
            constraints.append(Constraint("period", f"{name}:{period}", evidence))

    entry: list[Rule] = []
    exit_rules: list[Rule] = []

    # --- moving-average crossover, the single most common request ------------
    ma_terms = [
        (name, period)
        for name, period, _ in indicators
        if name in {"EMA", "SMA"} and period is not None
    ]
    cross_above = re.search(_CROSS_ABOVE, text, re.I)
    cross_below = re.search(_CROSS_BELOW, text, re.I)

    if len(ma_terms) >= 2 and (cross_above or cross_below):
        fast_name, fast_period = ma_terms[0]
        slow_name, slow_period = ma_terms[1]
        # Whichever period is smaller is the fast leg, regardless of mention order.
        if fast_period > slow_period:
            (fast_name, fast_period), (slow_name, slow_period) = (
                (slow_name, slow_period),
                (fast_name, fast_period),
            )
        fast = _term_for(fast_name, fast_period)
        slow = _term_for(slow_name, slow_period)
        if fast and slow:
            if cross_above:
                entry.append(Rule(left=fast, op="crosses_above", right=slow))
                constraints.append(
                    Constraint("operator", "entry:crosses_above", cross_above.group(0))
                )
            if cross_below:
                rule = Rule(left=fast, op="crosses_below", right=slow)
                (entry if not cross_above else exit_rules).append(rule)
                constraints.append(
                    Constraint(
                        "operator",
                        ("exit" if cross_above else "entry") + ":crosses_below",
                        cross_below.group(0),
                    )
                )
    else:
        # --- price against a single indicator --------------------------------
        for name, period, _evidence in indicators:
            term = _term_for(name, period)
            if term is None:
                continue
            if name == "RSI":
                below = re.search(
                    r"(?:rsi[^.]{0,30}?)?(?:below|under|less\s+than|<)\s*(\d{1,3})", text, re.I
                )
                above = re.search(
                    r"(?:rsi[^.]{0,30}?)?(?:above|over|greater\s+than|>)\s*(\d{1,3})", text, re.I
                )
                oversold = re.search(r"\boversold\b", text, re.I)
                overbought = re.search(r"\boverbought\b", text, re.I)
                if below:
                    entry.append(
                        Rule(
                            left=term,
                            op="below",
                            right=Term(kind="const", value=float(below.group(1))),
                        )
                    )
                    constraints.append(Constraint("operator", "entry:below", below.group(0)))
                elif oversold:
                    entry.append(Rule(left=term, op="below", right=Term(kind="const", value=30.0)))
                    constraints.append(Constraint("operator", "entry:below", oversold.group(0)))
                if above and not below:
                    entry.append(
                        Rule(
                            left=term,
                            op="above",
                            right=Term(kind="const", value=float(above.group(1))),
                        )
                    )
                    constraints.append(Constraint("operator", "entry:above", above.group(0)))
                elif overbought and not below:
                    exit_rules.append(
                        Rule(left=term, op="above", right=Term(kind="const", value=70.0))
                    )
                continue
            if cross_above and not entry:
                entry.append(
                    Rule(left=Term(kind="price", field="close"), op="crosses_above", right=term)
                )
                constraints.append(
                    Constraint("operator", "entry:crosses_above", cross_above.group(0))
                )
            elif cross_below and not entry:
                entry.append(
                    Rule(left=Term(kind="price", field="close"), op="crosses_below", right=term)
                )
                constraints.append(
                    Constraint("operator", "entry:crosses_below", cross_below.group(0))
                )
            elif (
                re.search(r"\b(?:price|close)\s+(?:is\s+)?(?:above|over)\b", text, re.I)
                and not entry
            ):
                entry.append(Rule(left=Term(kind="price", field="close"), op="above", right=term))
                constraints.append(Constraint("operator", "entry:above", "price above"))
            elif (
                re.search(r"\b(?:price|close)\s+(?:is\s+)?(?:below|under)\b", text, re.I)
                and not entry
            ):
                entry.append(Rule(left=Term(kind="price", field="close"), op="below", right=term))
                constraints.append(Constraint("operator", "entry:below", "price below"))

    # --- volume confirmation --------------------------------------------------
    # "volume is above 1.5x its 20-period average" is a single comparison against a
    # scaled VOL_SMA. It is handled separately because it is almost always an EXTRA
    # condition on top of a price rule rather than the rule itself, so folding it
    # into the loops above would either overwrite the price entry or be skipped.
    #
    # The semantic checker found this gap: the extractor was recognising the
    # VOL_SMA constraint from the text and then not building a rule for it, so it
    # correctly reported that the strategy was missing something the request asked
    # for. That is the checker doing its job on its own author.
    volume_rule = re.search(
        r"volume\s+(?:is\s+)?(?:above|over|greater\s+than|more\s+than|exceeds?|at\s+least)\s*"
        r"(?P<mult>\d+(?:\.\d+)?)\s*(?:x|times)\s*"
        r"(?:its\s+|the\s+)?(?P<period>\d{1,4})\s*-?\s*(?:period|day|bar)?\s*"
        r"(?:average|avg|volume\s+average|moving\s+average)",
        text,
        re.I,
    )
    if volume_rule:
        multiplier = float(volume_rule.group("mult"))
        vol_period = float(volume_rule.group("period"))
        entry.append(
            Rule(
                left=Term(kind="price", field="volume"),
                op="above",
                right=Term(
                    kind="indicator",
                    indicator="VOL_SMA",
                    params={"period": vol_period},
                    multiplier=multiplier,
                ),
            )
        )
        constraints.append(Constraint("operator", "entry:above", volume_rule.group(0)))

    # --- risk and sizing -----------------------------------------------------
    stop, stop_evidence = _percent(
        text,
        r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*(?:stop[- ]loss|stop)",
        r"stop(?:[- ]loss)?\s*(?:of|at|:)?\s*(?P<pct>\d+(?:\.\d+)?)\s*%",
    )
    if stop is not None:
        constraints.append(Constraint("stop", f"{stop:.4f}", stop_evidence))
    target, target_evidence = _percent(
        text,
        r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*(?:take[- ]profit|profit\s+target|target)",
        r"(?:take[- ]profit|profit\s+target|target)\s*(?:of|at|:)?\s*(?P<pct>\d+(?:\.\d+)?)\s*%",
    )
    if target is not None:
        constraints.append(Constraint("target", f"{target:.4f}", target_evidence))
    trailing, trailing_evidence = _percent(
        text,
        r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*trailing",
        r"trailing\s*(?:stop)?\s*(?:of|at|:)?\s*(?P<pct>\d+(?:\.\d+)?)\s*%",
    )
    if trailing is not None:
        constraints.append(Constraint("trailing", f"{trailing:.4f}", trailing_evidence))

    risk_per_trade, risk_evidence = _percent(
        text,
        r"risk(?:ing)?\s*(?:only\s*)?(?P<pct>\d+(?:\.\d+)?)\s*%",
        r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*(?:of\s+(?:equity|capital|account)\s+)?per\s+trade",
    )
    # ATR used as the RISK UNIT ("size using 2x the 14-period ATR") is a sizing
    # instruction, not a comparison. It produced no rule and no sizing change, so the
    # ATR the user explicitly asked for simply vanished — and the semantic checker
    # correctly flagged the indicator as missing.
    atr_sizing = re.search(
        r"(?:size|sizing|position)[^.]{0,60}?(?P<mult>\d+(?:\.\d+)?)\s*(?:x|times)\s*"
        r"(?:the\s+)?(?:(?P<period>\d{1,4})\s*-?\s*(?:period|day|bar)?\s*)?atr"
        r"|atr[^.]{0,30}?(?:as|for)\s+the\s+risk\s+unit",
        text,
        re.I,
    )

    sizing = SizingIntent()
    if atr_sizing is not None:
        groups = atr_sizing.groupdict()
        atr_multiple = groups.get("mult")
        raw_period = groups.get("period")
        if raw_period:
            atr_period = int(raw_period)
        else:
            # The period may have been written next to the indicator rather than next
            # to the sizing phrase ("...the 14-period ATR"), so fall back to whatever
            # the indicator scan already found before defaulting.
            named = next((p for n, p, _ in indicators if n == "ATR" and p), None)
            atr_period = int(named) if named else 14
        sizing = SizingIntent(
            method="atr",
            value=float(atr_multiple) if atr_multiple else 2.0,
            atr_period=atr_period,
        )
        constraints.append(Constraint("sizing", f"atr:{atr_period}", atr_sizing.group(0)))
    elif risk_per_trade is not None and stop is not None:
        sizing = SizingIntent(method="risk_per_trade", value=risk_per_trade)
        constraints.append(
            Constraint("sizing", f"risk_per_trade:{risk_per_trade:.4f}", risk_evidence)
        )
    elif risk_per_trade is not None:
        sizing = SizingIntent(method="percent_equity", value=risk_per_trade)
        constraints.append(
            Constraint("sizing", f"percent_equity:{risk_per_trade:.4f}", risk_evidence)
        )

    time_exit = None
    bars_match = re.search(
        r"(?:exit|close|hold)\s*(?:after|for)\s*(\d{1,4})\s*(?:bars?|candles?|periods?)", text, re.I
    )
    if bars_match:
        time_exit = int(bars_match.group(1))

    ambiguities = [
        reason for pattern, reason in _AMBIGUOUS_PATTERNS if re.search(pattern, text, re.I)
    ]
    unsupported = [
        reason for pattern, reason in _UNSUPPORTED_PATTERNS if re.search(pattern, text, re.I)
    ]

    intent = StrategyIntent(
        symbol=symbol,
        timeframe=timeframe,
        entry=entry,
        exit=ExitIntent(
            stop_loss_pct=stop,
            take_profit_pct=target,
            trailing_stop_pct=trailing,
            time_exit_bars=time_exit,
            rules=exit_rules,
        ),
        sizing=sizing,
        risk=RiskIntent(max_position_pct=0.25),
        ambiguities=ambiguities,
        unsupported=unsupported,
    )

    # Operand-level constraints, one per rule the extractor was confident enough to
    # BUILD. Checking indicators, periods and operators separately is not enough:
    # a local model produced a correct entry (EMA 20 crosses above EMA 50) and an
    # exit of "EMA 20 crosses below 0" — every individual constraint was satisfied
    # somewhere in the strategy, so nothing was flagged, while the exit rule was
    # nonsense. Comparing the OPERAND SET of each rule catches that.
    #
    # Deliberately unordered and operator-free: "A crosses below B" and
    # "B crosses above A" describe the same event, and failing a model for choosing
    # the other form would be a false positive. The operator itself is already
    # checked by the separate `operator` constraints.
    for rule in entry:
        constraints.append(
            Constraint("rule_operands", f"entry:{_operand_key(rule)}", rule.signature())
        )
    for rule in exit_rules:
        constraints.append(
            Constraint("rule_operands", f"exit:{_operand_key(rule)}", rule.signature())
        )
    return Extraction(intent=intent, constraints=constraints)


def _operand_key(rule: Rule) -> str:
    """Unordered identity of a rule's two operands."""
    return "|".join(sorted((rule.left.signature(), rule.right.signature())))


def extract_intent(request: str) -> StrategyIntent:
    """Convenience wrapper used by the deterministic provider."""
    return extract(request).intent


# --------------------------------------------------------------------------- #
# Semantic verification
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SemanticIssue:
    constraint: Constraint
    problem: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.constraint.kind,
            "expected": self.constraint.detail,
            "evidence": self.constraint.evidence,
            "problem": self.problem,
        }


def verify(request: str, produced: StrategyIntent) -> list[SemanticIssue]:
    """Check a produced intent against what the request unambiguously asked for.

    Only constraints the extractor is CONFIDENT about are checked. A schema-valid
    strategy that quietly swapped EMA for SMA, or 20 for 10, is the failure mode
    this exists to catch, and it is invisible to schema validation.
    """
    extraction = extract(request)
    issues: list[SemanticIssue] = []

    all_rules = list(produced.entry) + list(produced.exit.rules)
    used_indicators = {
        term.indicator
        for rule in all_rules
        for term in (rule.left, rule.right)
        if term.kind == "indicator" and term.indicator
    }
    used_periods = {
        f"{term.indicator}:{int(period)}"
        for rule in all_rules
        for term in (rule.left, rule.right)
        if term.kind == "indicator" and term.indicator
        for key, period in term.params.items()
        if key == "period"
    }
    # An indicator can be used for SIZING rather than in a comparison. ATR sizing is
    # the common case, and treating it as "unused" would report a false difference
    # from the request — the surest way to teach users to ignore the checker.
    if produced.sizing.method == "atr":
        used_indicators.add("ATR")
        if produced.sizing.atr_period:
            used_periods.add(f"ATR:{int(produced.sizing.atr_period)}")
    entry_ops = {f"entry:{rule.op}" for rule in produced.entry}
    exit_ops = {f"exit:{rule.op}" for rule in produced.exit.rules}

    for constraint in extraction.constraints:
        if constraint.kind == "indicator":
            if constraint.detail not in used_indicators:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request names {constraint.detail} but the strategy uses "
                        f"{sorted(used_indicators) or 'no indicators'}",
                    )
                )
        elif constraint.kind == "period":
            if constraint.detail not in used_periods:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request specifies {constraint.detail.replace(':', ' period ')} "
                        f"but the strategy uses {sorted(used_periods) or 'no periods'}",
                    )
                )
        elif constraint.kind == "operator":
            side, _, op = constraint.detail.partition(":")
            pool = entry_ops if side == "entry" else exit_ops
            if constraint.detail not in pool:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request asks for '{op}' on {side} but the strategy has "
                        f"{sorted(pool) or 'nothing'} there",
                    )
                )
        elif constraint.kind == "timeframe":
            if produced.timeframe is not None and produced.timeframe != constraint.detail:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request asks for {constraint.detail} but the strategy is "
                        f"{produced.timeframe}",
                    )
                )
        elif constraint.kind == "symbol":
            if produced.symbol is not None and produced.symbol != constraint.detail:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request names {constraint.detail} but the strategy targets "
                        f"{produced.symbol}",
                    )
                )
        elif constraint.kind == "rule_operands":
            side, _, key = constraint.detail.partition(":")
            produced_rules = produced.entry if side == "entry" else produced.exit.rules
            produced_keys = {_operand_key(rule) for rule in produced_rules}
            if key not in produced_keys:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request's {side} rule compares {key.replace('|', ' and ')}, but "
                        f"the strategy's {side} rules compare "
                        f"{sorted(k.replace('|', ' and ') for k in produced_keys) or 'nothing'}",
                    )
                )
        elif constraint.kind in {"stop", "target", "trailing"}:
            expected = float(constraint.detail)
            actual = {
                "stop": produced.exit.stop_loss_pct,
                "target": produced.exit.take_profit_pct,
                "trailing": produced.exit.trailing_stop_pct,
            }[constraint.kind]
            if actual is None or abs(actual - expected) > 1e-6:
                issues.append(
                    SemanticIssue(
                        constraint,
                        f"the request specifies a {constraint.kind} of {expected:.2%} but the "
                        f"strategy has {'none' if actual is None else format(actual, '.2%')}",
                    )
                )
    return issues
