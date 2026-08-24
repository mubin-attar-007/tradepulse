"""The evaluation runner.

Runs the whole NL→spec pipeline over a dataset and reports metrics that are
CHECKED, not judged. No LLM grades another LLM here: every assertion reduces to
"does this indicator appear", "is this period present", "was this refused" — things
a reader can verify by hand from the report.

The metric that matters most is deliberately not "schema-valid rate". Schema
validity was the v1 measure and it is close to meaningless: a strategy can be
perfectly valid JSON and the wrong strategy entirely. The headline here is
**semantic accuracy** — the share of requests answered with the strategy that was
actually asked for.

Runs against any profile, so the same dataset produces a comparable score for the
deterministic compiler, a local 3B model, and a hosted model. Results carry the
profile, prompt version and dataset version, because a score without those is not
a measurement of anything.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.modules.ai import prompts
from app.modules.ai.ir import StrategyIntent
from app.modules.ai.service import AIService, GenerationResult
from app.modules.evaluations.cases import DATASET_VERSION, EvalCase

logger = get_logger("evaluations")


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    status: str = ""
    tokens: int = 0
    latency_ms: float = 0.0
    repairs: int = 0
    semantic_issues: int = 0
    deterministic: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "failures": self.failures,
            "status": self.status,
            "tokens": self.tokens,
            "latency_ms": round(self.latency_ms, 1),
            "repairs": self.repairs,
            "semantic_issues": self.semantic_issues,
            "deterministic": self.deterministic,
        }


@dataclass
class EvalReport:
    profile: str
    dataset_version: str
    prompt_version: str
    results: list[CaseResult] = field(default_factory=list)
    wall_clock_seconds: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def by_category(self) -> dict[str, dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for result in self.results:
            bucket = buckets.setdefault(
                result.category, {"total": 0, "passed": 0, "tokens": 0, "latency_ms": 0.0}
            )
            bucket["total"] += 1
            bucket["passed"] += int(result.passed)
            bucket["tokens"] += result.tokens
            bucket["latency_ms"] += result.latency_ms
        for bucket in buckets.values():
            bucket["pass_rate"] = round(bucket["passed"] / bucket["total"], 4)
            bucket["mean_latency_ms"] = round(bucket["latency_ms"] / bucket["total"], 1)
        return buckets

    def as_dict(self) -> dict[str, Any]:
        totals = self.by_category()
        return {
            "profile": self.profile,
            "dataset_version": self.dataset_version,
            "prompt_version": self.prompt_version,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.passed / self.total, 4) if self.total else 0.0,
            "wall_clock_seconds": round(self.wall_clock_seconds, 1),
            "total_tokens": sum(r.tokens for r in self.results),
            "mean_latency_ms": (
                round(sum(r.latency_ms for r in self.results) / self.total, 1) if self.total else 0
            ),
            "repair_rate": (
                round(sum(1 for r in self.results if r.repairs) / self.total, 4)
                if self.total
                else 0.0
            ),
            "by_category": totals,
            "results": [r.as_dict() for r in self.results],
        }

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]


def _intent_of(result: GenerationResult) -> StrategyIntent | None:
    return result.intent


def grade(case: EvalCase, result: GenerationResult) -> list[str]:
    """Every way this answer failed the case. Empty means it passed."""
    failures: list[str] = []
    expect = case.expect

    if expect.status and result.status != expect.status:
        failures.append(f"status: expected {expect.status}, got {result.status} ({result.message})")

    for fragment in expect.unsupported_contains:
        if not any(fragment in reason for reason in result.unsupported):
            failures.append(f"missing refusal reason containing {fragment!r}")
    for fragment in expect.ambiguity_contains:
        if not any(fragment in reason for reason in result.ambiguities):
            failures.append(f"missing clarification containing {fragment!r}")
    if expect.expect_no_ambiguity and result.ambiguities:
        # Over-asking is a real failure: a tool that questions a clear request
        # teaches its user to ignore the questions.
        failures.append(f"unnecessary clarification: {result.ambiguities}")

    # Everything below needs a strategy to inspect. A refusal case legitimately has
    # none, so only complain when the case expected one.
    intent = _intent_of(result)
    wants_strategy = bool(
        expect.indicators
        or expect.periods
        or expect.entry_ops
        or expect.exit_ops
        or expect.symbol
        or expect.timeframe
        or expect.stop_loss_pct is not None
        or expect.take_profit_pct is not None
        or expect.trailing_stop_pct is not None
        or expect.sizing_method
    )
    if not wants_strategy:
        return failures
    if intent is None or result.spec is None:
        failures.append(f"no strategy produced ({result.status}: {result.message[:120]})")
        return failures

    rules = list(intent.entry) + list(intent.exit.rules)
    used_indicators = {
        term.indicator
        for rule in rules
        for term in (rule.left, rule.right)
        if term.kind == "indicator" and term.indicator
    }
    used_periods = {
        f"{term.indicator}:{int(value)}"
        for rule in rules
        for term in (rule.left, rule.right)
        if term.kind == "indicator" and term.indicator
        for key, value in term.params.items()
        if key == "period"
    }

    for indicator in expect.indicators:
        if indicator not in used_indicators:
            failures.append(f"indicator {indicator} missing (used {sorted(used_indicators)})")
    for period in expect.periods:
        if period not in used_periods:
            failures.append(f"period {period} missing (used {sorted(used_periods)})")
    for op in expect.entry_ops:
        if op not in {rule.op for rule in intent.entry}:
            failures.append(f"entry operator {op} missing")
    for op in expect.exit_ops:
        if op not in {rule.op for rule in intent.exit.rules}:
            failures.append(f"exit operator {op} missing")
    if expect.symbol and intent.symbol != expect.symbol:
        failures.append(f"symbol: expected {expect.symbol}, got {intent.symbol}")
    if expect.timeframe and intent.timeframe != expect.timeframe:
        failures.append(f"timeframe: expected {expect.timeframe}, got {intent.timeframe}")

    for name, expected in (
        ("stop_loss_pct", expect.stop_loss_pct),
        ("take_profit_pct", expect.take_profit_pct),
        ("trailing_stop_pct", expect.trailing_stop_pct),
    ):
        if expected is None:
            continue
        actual = getattr(intent.exit, name)
        if actual is None or abs(actual - expected) > 1e-6:
            failures.append(f"{name}: expected {expected}, got {actual}")
    if expect.sizing_method and intent.sizing.method != expect.sizing_method:
        failures.append(f"sizing: expected {expect.sizing_method}, got {intent.sizing.method}")
    return failures


async def run_evaluation(
    cases: list[EvalCase],
    redis: Redis,
    *,
    profile: str | None = None,
    settings: Settings | None = None,
) -> EvalReport:
    """Run every case and grade it. One user id per run keeps budgets isolated."""
    settings = settings or get_settings()
    service = AIService(redis, settings)
    report = EvalReport(
        profile=profile or ",".join(settings.ai_profile_chain),
        dataset_version=DATASET_VERSION,
        prompt_version=prompts.STRATEGY_IR.id,
    )
    user_id = uuid.uuid4()
    started = time.perf_counter()

    for case in cases:
        try:
            result = await service.generate_strategy(
                case.request, user_id, profile_override=profile
            )
        except Exception as exc:  # a crash is a failing case, not a crashed run
            report.results.append(
                CaseResult(
                    case_id=case.id,
                    category=case.category,
                    passed=False,
                    failures=[f"raised {type(exc).__name__}: {exc}"],
                    status="error",
                )
            )
            continue

        failures = grade(case, result)
        report.results.append(
            CaseResult(
                case_id=case.id,
                category=case.category,
                passed=not failures,
                failures=failures,
                status=result.status,
                tokens=result.total_tokens,
                latency_ms=result.total_latency_ms,
                repairs=max(0, len(result.attempts) - 1),
                semantic_issues=len(result.semantic_issues),
                deterministic=result.deterministic_only,
            )
        )

    report.wall_clock_seconds = time.perf_counter() - started
    logger.info(
        "evaluation_complete",
        profile=report.profile,
        passed=report.passed,
        total=report.total,
    )
    return report
