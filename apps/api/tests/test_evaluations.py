"""The AI evaluation suite as a CI gate.

Runs the whole dataset against the deterministic provider on every commit. It needs
no API key, no model download and no network, and it completes in about a second —
which is the entire reason the deterministic provider exists.

What this protects: the pipeline's SEMANTICS. A change to the extractor, the IR, the
compiler, or the DSL that quietly alters how a request is interpreted shows up here
as a specific failing case with a specific reason, rather than as a subtly different
strategy nobody notices until a backtest looks wrong.

Model-backed evaluation (local or hosted) is run deliberately rather than in CI:
    uv run python -m app.cli.evaluate --profile local-balanced
because it is slow, hardware-dependent, and would make CI's result a measurement of
the runner rather than of the change.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.modules.evaluations.cases import EvalCase, load_cases
from app.modules.evaluations.runner import run_evaluation

# Categories the NL->spec grader can actually judge. `grounding` cases describe
# narration expectations for a future narration runner; grading them here would
# report failures that mean nothing.
GRADED = {"valid", "ambiguous", "unsupported", "safety", "injection"}


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AI_PROFILE_CHAIN_RAW", "deterministic")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_dataset_loads_and_is_substantial() -> None:
    cases = load_cases()
    by_category: dict[str, int] = {}
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1

    assert by_category.get("valid", 0) >= 100
    assert by_category.get("ambiguous", 0) >= 30
    assert by_category.get("unsupported", 0) >= 30
    assert by_category.get("safety", 0) >= 30
    assert by_category.get("injection", 0) >= 20
    assert len(cases) >= 235


def test_every_case_is_reviewable() -> None:
    """A case a human cannot read is a case nobody will maintain."""
    for case in load_cases():
        assert case.notes, f"{case.id} has no notes explaining what it tests"
        assert case.request.strip(), f"{case.id} has an empty request"
        assert case.id and case.category


def test_valid_cases_assert_something_specific() -> None:
    """A 'valid' case that asserts nothing passes trivially and measures nothing."""
    for case in load_cases(categories={"valid"}):
        expect = case.expect
        asserted = (
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
        assert asserted, f"{case.id} asserts nothing about the produced strategy"


async def test_the_suite_passes_against_the_deterministic_compiler() -> None:
    """The regression gate.

    A failure here names the exact case and the exact difference, so a semantic
    regression is diagnosable rather than merely visible.
    """
    cases: list[EvalCase] = load_cases(categories=GRADED)
    report = await run_evaluation(cases, get_redis_client(), profile="deterministic")

    failures = report.failures()
    detail = "\n".join(f"  {r.case_id}: {'; '.join(r.failures)}" for r in failures[:20])
    assert not failures, f"{len(failures)} evaluation case(s) failed:\n{detail}"
    assert report.total == len(cases)


async def test_safety_and_refusal_cases_never_produce_a_strategy() -> None:
    """The hard gate: a request the platform refuses must not come back with a
    strategy attached, whatever else changes."""
    cases = load_cases(categories={"unsupported"})
    report = await run_evaluation(cases, get_redis_client(), profile="deterministic")
    for result in report.results:
        assert result.status in {"refused", "needs_clarification"}, (
            f"{result.case_id} returned {result.status}"
        )


async def test_the_report_carries_the_provenance_a_score_needs() -> None:
    """A pass rate without a profile, prompt version and dataset version is not a
    measurement of anything."""
    cases = load_cases(categories={"valid"})[:5]
    report = await run_evaluation(cases, get_redis_client(), profile="deterministic")
    payload = report.as_dict()
    assert payload["profile"] == "deterministic"
    assert payload["prompt_version"].startswith("strategy_ir@")
    assert payload["dataset_version"]
    assert payload["by_category"]["valid"]["total"] == 5
