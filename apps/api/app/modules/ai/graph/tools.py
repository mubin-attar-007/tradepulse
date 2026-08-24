"""The graph's entire capability surface.

This module IS the sandbox. The agent can do exactly what is defined here and
nothing else — there is no code execution, no SQL string, no shell, no HTTP client,
no secret access, and no order placement, because none of those functions exist for
it to call. Safety is a property of the available tools, not of an instruction in a
prompt asking the model to behave.

Every tool is:
* **typed** — arguments and return shapes are fixed, so a model cannot smuggle
  behaviour through a free-form field;
* **owner-scoped** — data access goes through the same owner-scoped repositories
  every HTTP handler uses, so the agent has no privileged read path;
* **deterministic** — the numbers come from the engine and the robustness lab, not
  from a model, so a citation in a report refers to something that was computed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.ai import compiler
from app.modules.backtesting.service import data_fingerprint
from app.modules.indicators.catalog import INDICATOR_PARAMS, outputs_for
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.robustness.overrides import Axis
from app.modules.robustness.service import MIN_BARS_FOR_ROBUSTNESS, RobustnessService
from app.modules.strategies.service import StrategyService
from app.modules.strategies.spec import StrategySpec

logger = get_logger("research_tools")

# How much history a planned experiment asks for. Bounded so a plan cannot become a
# request to scan every bar the platform holds.
DEFAULT_LOOKBACK = timedelta(days=365)


def list_supported_indicators() -> list[dict[str, Any]]:
    """The closed catalog, with each entry's required parameters and outputs."""
    return [
        {
            "type": name,
            "params": {p: {"min": lo, "max": hi} for p, (lo, hi) in params.items()},
            "outputs": list(outputs_for(name)),
        }
        for name, params in INDICATOR_PARAMS.items()
    ]


def classify_request(request: str) -> tuple[str, str]:
    """Label the request from explicit patterns, not from a model.

    Returns ``(label, reason)``. The distinction that actually matters — is this a
    strategy, or something the platform refuses? — is answered by the same detector
    the compiler uses, so classification and refusal can never disagree.
    """
    extraction = compiler.extract(request)
    if extraction.intent.unsupported:
        return "unsupported", "; ".join(extraction.intent.unsupported)
    if extraction.intent.entry:
        return "strategy", f"{len(extraction.constraints)} explicit constraint(s) recognised"
    if extraction.constraints:
        return "unclear", "some details recognised, but no entry rule could be identified"
    return "unclear", "no strategy rule could be identified in the request"


def understand_request(request: str) -> dict[str, Any]:
    """Everything the deterministic layer can say about a request, with no model."""
    extraction = compiler.extract(request)
    intent = extraction.intent
    entry = [rule.signature() for rule in intent.entry]
    return {
        "symbol": intent.symbol,
        "timeframe": intent.timeframe,
        "entry_rules": entry,
        "exit_rules": [rule.signature() for rule in intent.exit.rules],
        "ambiguities": intent.ambiguities,
        "unsupported": intent.unsupported,
        "constraints": [
            {"kind": c.kind, "detail": c.detail, "evidence": c.evidence}
            for c in extraction.constraints
        ],
        "hypothesis": (
            f"Entering {intent.symbol or 'the selected instrument'} on "
            f"{intent.timeframe or 'the selected timeframe'} when {' and '.join(entry)} "
            "produces a positive risk-adjusted result net of modelled costs."
            if entry
            else "No testable rule was identified in the request."
        ),
    }


async def inspect_dataset(session: AsyncSession, symbol: str, timeframe: str) -> dict[str, Any]:
    """What data exists for an instrument — before promising an experiment over it."""
    instrument = await session.scalar(select(Instrument).where(Instrument.symbol == symbol))
    if instrument is None:
        return {"available": False, "reason": f"{symbol} is not a seeded instrument"}
    end = datetime.now(UTC)
    bars = await md_repo.get_bars(
        session, instrument.id, timeframe=timeframe, start=end - DEFAULT_LOOKBACK, end=end
    )
    gaps = sum(1 for b in bars if b.bar_count is not None and b.bar_count < _expected(timeframe))
    return {
        "available": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "calendar": instrument.calendar,
        "bars": len(bars),
        "first": bars[0].ts.isoformat() if bars else None,
        "last": bars[-1].ts.isoformat() if bars else None,
        # A bucket built from fewer 1-minute bars than a full interval is a venue gap,
        # not a data error — but a plan that ignores them overstates its coverage.
        "incomplete_buckets": gaps,
        "fingerprint": data_fingerprint(instrument.id, timeframe, bars) if bars else "",
    }


def _expected(timeframe: str) -> int:
    return {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe, 1)


async def build_experiment_plan(
    session: AsyncSession, spec: dict[str, Any]
) -> tuple[dict[str, Any], str, str]:
    """Turn a proposed strategy into a concrete, bounded plan.

    Returns ``(plan, data_fingerprint, problem)``. A non-empty ``problem`` means the
    plan cannot be honoured — reported plainly rather than by producing a plan that
    would fail halfway through.
    """
    parsed = StrategySpec.model_validate(spec)
    symbol, timeframe = parsed.universe[0], parsed.timeframe
    dataset = await inspect_dataset(session, symbol, timeframe)
    if not dataset["available"]:
        return {}, "", dataset["reason"]
    if dataset["bars"] < MIN_BARS_FOR_ROBUSTNESS:
        return (
            {},
            "",
            f"Only {dataset['bars']} closed {timeframe} bars are held for {symbol}; "
            f"robustness analysis needs at least {MIN_BARS_FOR_ROBUSTNESS}. Backfill more "
            "history before running this experiment.",
        )

    # Sweep the periods the strategy actually uses, one axis at a time, so the grid
    # stays small enough that the multiple-testing correction remains meaningful.
    axes: list[dict[str, Any]] = []
    for indicator in parsed.indicators[:1]:
        period = indicator.params.get("period")
        if period:
            base = int(period)
            values = sorted({max(2, base // 2), base, base * 2})
            axes.append({"path": f"indicators.{indicator.id}.params.period", "values": values})

    plan = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": dataset["bars"],
        "start": dataset["first"],
        "end": dataset["last"],
        "analyses": ["backtest", "walk_forward", "cost_stress", "monte_carlo"]
        + (["parameter_sensitivity"] if axes else []),
        "walk_forward_folds": 4,
        "cost_multiples": [1.0, 1.5, 2.0, 3.0, 5.0],
        "monte_carlo_samples": 1000,
        "seed": 7,
        "axes": axes,
        "incomplete_buckets": dataset["incomplete_buckets"],
    }
    return plan, dataset["fingerprint"], ""


async def run_planned_experiment(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    spec: dict[str, Any] | None,
    plan: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    """Execute an APPROVED plan. Returns ``(experiment_id, evidence, problem)``.

    The strategy is saved first so the experiment references a real, versioned
    strategy the user owns — an experiment pointing at an anonymous blob is not
    reproducible from the UI, whatever its hashes say.
    """
    if spec is None:
        return "", {}, "no strategy to run"
    parsed = StrategySpec.model_validate(spec)
    strategy, _version = await StrategyService(session, owner_id).create(parsed)
    await session.flush()

    start = datetime.fromisoformat(plan["start"]) if plan.get("start") else None
    end = datetime.fromisoformat(plan["end"]) if plan.get("end") else None
    if start is None or end is None:
        return "", {}, "the plan does not name a data window"

    axes = tuple(
        Axis(path=a["path"], values=tuple(float(v) for v in a["values"]))
        for a in plan.get("axes", [])
    )
    experiment = await RobustnessService(session, owner_id).run_suite(
        strategy.id,
        start=start,
        # `end` is the last bar's OPEN; widen by one interval so it is included.
        end=end + timedelta(days=1),
        folds=int(plan.get("walk_forward_folds", 4)),
        axes=axes,
        cost_multiples=plan.get("cost_multiples", (1.0, 2.0, 3.0)),
        monte_carlo_samples=int(plan.get("monte_carlo_samples", 1000)),
        seed=int(plan.get("seed", 7)),
    )
    if experiment.status != "done":
        return str(experiment.id), {}, experiment.error or "the experiment failed"
    return str(experiment.id), experiment.result or {}, ""


def build_report(state: dict[str, Any]) -> dict[str, Any]:
    """Assemble the research report from the experiment record.

    Deterministic by construction: every figure is copied from the persisted
    experiment and carries a citation naming where it came from. There is no step
    here where a number could be produced by a model, which is what makes the
    report's claims checkable rather than merely plausible.
    """
    evidence = state.get("evidence") or {}
    baseline = (evidence.get("baseline") or {}).get("metrics") or {}
    stability = evidence.get("stability") or {}
    walk = evidence.get("walk_forward") or {}
    costs = evidence.get("cost_stress") or {}
    experiment_id = state.get("experiment_id", "")

    citations = [
        {
            "claim": "headline metrics",
            "source": f"experiment:{experiment_id}",
            "path": "baseline.metrics",
        },
        {
            "claim": "out-of-sample behaviour",
            "source": f"experiment:{experiment_id}",
            "path": "walk_forward",
        },
        {
            "claim": "cost sensitivity",
            "source": f"experiment:{experiment_id}",
            "path": "cost_stress",
        },
        {
            "claim": "robustness verdict",
            "source": f"experiment:{experiment_id}",
            "path": "stability",
        },
    ]

    findings: list[str] = []
    for check in stability.get("checks", []):
        if check.get("verdict") in {"fail", "warn"}:
            findings.append(f"{check['name']}: {check['detail']}")
    if not findings:
        findings.append("No robustness check raised a concern on the analyses that ran.")

    return {
        "hypothesis": state.get("hypothesis"),
        "verdict": stability.get("verdict"),
        "summary": stability.get("summary"),
        "headline_metrics": {
            k: baseline.get(k)
            for k in ("total_return", "max_drawdown", "num_trades", "win_rate", "sharpe")
        },
        "out_of_sample": {
            "compounded_return": walk.get("oos_total_return"),
            "fold_consistency": walk.get("consistency"),
        },
        "cost_breakeven_multiple": costs.get("breakeven_multiple"),
        "findings": findings,
        "applied_defaults": state.get("applied_defaults", []),
        "semantic_issues": state.get("semantic_issues", []),
        "citations": citations,
        "reproduce": {
            "experiment_id": experiment_id,
            "spec_hash": state.get("spec_hash"),
            "data_fingerprint": state.get("data_fingerprint"),
            "plan_hash": state.get("plan_hash"),
        },
        "disclosure": (
            "Historical simulation under the displayed assumptions. Results are "
            "hypothetical, are not achievable returns, and do not predict future "
            "performance. This is not investment advice."
        ),
    }
