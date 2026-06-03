"""System prompts + prompt builders. The DSL guide + a worked example steer the
model far more reliably than dumping the raw JSON Schema; the validate/repair
loop in the service catches the rest."""

from __future__ import annotations

import json
from typing import Any

from app.modules.strategies.spec import example_composite_spec

STRATEGY_SYSTEM = (
    "You are a quantitative strategy assistant. Convert the user's request into a single "
    "StrategySpec JSON object. Output ONLY the JSON object - no prose, no markdown fences. "
    "Every strategy MUST include an `exit` (at least one of stop_loss_pct, take_profit_pct, "
    "trailing_stop_pct, time_exit_bars), a `sizing`, and `risk` limits. Use only indicators "
    "from the catalog. You are not giving financial advice."
)

DSL_GUIDE = """\
StrategySpec JSON fields:
- spec_version: "1.0"
- name: string
- universe: [symbol]   e.g. ["BTC/USD"]
- timeframe: one of 1m, 5m, 15m, 1h, 4h, 1d
- indicators: [{id, type, params}] where type/params is one of:
    EMA{period} SMA{period} RSI{period} ATR{period} BBANDS{period,std}
    MACD{fast,slow,signal} VWAP{} VOL_SMA{period}
- entry_long: Condition (required). entry_short: Condition (optional).
- exit (required): {stop_loss_pct, take_profit_pct, trailing_stop_pct,
    time_exit_bars, exit_conditions} - at least one must be set
- sizing (required): {method: fixed_units|percent_equity|risk_per_trade|atr, value, atr_ref?}
- risk: {max_position_pct (0-1), max_open_positions, max_daily_loss_pct?,
    max_consecutive_losses?}
- time_of_day (optional): {start "HH:MM", end "HH:MM", timezone exchange|utc}

A Condition is either:
  {"type":"compare","left":Operand,"op":OP,"right":Operand}
    where OP is one of: > < >= <= cross_above cross_below
  {"type":"group","logic":"all"|"any","conditions":[Condition, ...]}
An Operand is one of:
  {"kind":"price","field":"open|high|low|close|volume"}
  {"kind":"indicator","ref":"<indicator id>","output":"upper|middle|lower|macd|signal|hist"}
    (output is required only for BBANDS/MACD)
  {"kind":"const","value": number}
  Any operand may add "multiplier" (default 1.0) and "offset" (default 0.0),
    so the effective value is multiplier*X + offset.
"""

NARRATION_SYSTEM = (
    "You are a trading-analytics assistant. Explain the backtest results plainly and "
    "concisely. Use ONLY the numbers present in the provided data - never invent, estimate, "
    "or extrapolate figures. Call out key risks you can see (e.g. drawdown, tiny sample size, "
    "negative Sharpe). End with exactly: 'This is not financial advice.'"
)


def build_strategy_prompt(
    nl: str, errors: str | None = None, last_output: str | None = None
) -> str:
    example = json.dumps(example_composite_spec().model_dump(mode="json"), indent=2)
    parts = [DSL_GUIDE, f"Example StrategySpec:\n{example}", f"User request: {nl}"]
    if errors and last_output:
        parts.append(
            "Your previous output was INVALID. Return corrected JSON only.\n"
            f"Previous output:\n{last_output}\n\nValidation errors:\n{errors}"
        )
    return "\n\n".join(parts)


def build_explain_prompt(context: dict[str, Any]) -> str:
    return "Backtest results (JSON):\n" + json.dumps(context, indent=2, default=str)
