"""Run the AI evaluation suite.

    uv run python -m app.cli.evaluate                        # deterministic, offline
    uv run python -m app.cli.evaluate --profile local-balanced
    uv run python -m app.cli.evaluate --categories valid,safety --out report.json

The default runs against the deterministic compiler, so it needs no key, no model
and no network — which is what lets CI run it on every commit. Pointing it at a
local or hosted profile produces a comparable score for the same dataset, and the
report records which profile, which prompt version and which dataset version
produced it, because a score without those is not a measurement of anything.

Exit code is non-zero when the pass rate falls below ``--min-pass-rate``, so the
same command works as a CI gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.core.redis import close_redis, get_redis_client
from app.modules.evaluations.cases import load_cases
from app.modules.evaluations.runner import EvalReport, run_evaluation


def _print_report(report: EvalReport) -> None:
    payload = report.as_dict()
    print()
    print(f"  profile          {report.profile}")
    print(f"  prompt           {report.prompt_version}")
    print(f"  dataset          {report.dataset_version}")
    print(f"  cases            {report.total}")
    print(f"  passed           {report.passed}  ({payload['pass_rate']:.1%})")
    print(f"  repair rate      {payload['repair_rate']:.1%}")
    print(f"  mean latency     {payload['mean_latency_ms']} ms")
    print(f"  total tokens     {payload['total_tokens']}")
    print(f"  wall clock       {report.wall_clock_seconds:.1f} s")
    print()
    print("  by category")
    for name, bucket in sorted(report.by_category().items()):
        print(
            f"    {name:<14} {bucket['passed']:>4}/{bucket['total']:<4} "
            f"{bucket['pass_rate']:>7.1%}   {bucket['mean_latency_ms']:>8.0f} ms"
        )

    failures = report.failures()
    if failures:
        print()
        print(f"  {len(failures)} failing case(s):")
        for result in failures[:25]:
            print(f"    {result.case_id} ({result.status})")
            for failure in result.failures[:3]:
                print(f"        - {failure}")
        if len(failures) > 25:
            print(f"    ... and {len(failures) - 25} more (see the JSON report)")
    print()


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the TradePulse AI evaluation suite.")
    parser.add_argument(
        "--profile",
        default=None,
        help="Model profile to evaluate (deterministic, local-small, local-balanced, "
        "local-quality, remote-fast). Defaults to the configured chain.",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated subset: valid, ambiguous, unsupported, safety, injection.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    parser.add_argument("--out", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.0,
        help="Exit non-zero below this pass rate, so this doubles as a CI gate.",
    )
    args = parser.parse_args()

    categories = (
        {c.strip() for c in args.categories.split(",") if c.strip()} if args.categories else None
    )
    # Grounding cases document narration expectations for a future narration runner;
    # grading them with the NL->spec grader would report meaningless failures.
    if categories is None:
        categories = {"valid", "ambiguous", "unsupported", "safety", "injection"}

    cases = load_cases(categories=categories)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No evaluation cases matched.", file=sys.stderr)
        return 2

    print(f"Running {len(cases)} case(s)...", file=sys.stderr)
    redis = get_redis_client()
    try:
        report = await run_evaluation(cases, redis, profile=args.profile)
    finally:
        await close_redis()

    payload = report.as_dict()
    _print_report(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  report written to {args.out}")

    pass_rate = float(payload["pass_rate"])
    if pass_rate < args.min_pass_rate:
        print(
            f"FAIL: pass rate {pass_rate:.1%} is below the required {args.min_pass_rate:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
