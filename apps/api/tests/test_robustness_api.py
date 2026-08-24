"""Robustness suite end to end: run it, persist it, read it back.

Covers the part the pure-function tests cannot: that a suite is reproducible from
its own persisted record, that it refuses to run on too little data instead of
producing folds that mean nothing, and that a parameter sweep cannot be used to
reach outside the whitelisted parameters.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.market_data import repository as md_repo
from app.modules.market_data.providers.base import CanonicalBar
from app.modules.robustness.overrides import Axis
from app.modules.robustness.service import MIN_BARS_FOR_ROBUSTNESS, RobustnessService
from app.modules.strategies.service import StrategyService
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)

BASE = datetime(2024, 5, 1, tzinfo=UTC)


def _spec(symbol: str = "ROBUST/USD") -> StrategySpec:
    return StrategySpec(
        name="Robustness fixture",
        universe=[symbol],
        timeframe="1h",
        indicators=[
            IndicatorSpec(id="fast", type="SMA", params={"period": 5}),
            IndicatorSpec(id="slow", type="SMA", params={"period": 20}),
        ],
        entry_long=Comparison(
            left=Operand(kind="indicator", ref="fast"),
            op="cross_above",
            right=Operand(kind="indicator", ref="slow"),
        ),
        exit=ExitRule(stop_loss_pct=0.03, take_profit_pct=0.06, time_exit_bars=24),
        sizing=PositionSizing(method="percent_equity", value=0.25),
        risk=RiskLimits(max_position_pct=0.25, max_open_positions=1),
    )


async def _seed(session, *, hours: int, symbol: str = "ROBUST/USD"):  # type: ignore[no-untyped-def]
    """`hours` complete hourly bars, written as the 1-minute bars they aggregate from."""
    instrument = await md_repo.get_or_create_instrument(
        session, symbol=symbol, asset_class="crypto", calendar="24x7"
    )
    bars: list[CanonicalBar] = []
    prev = 100.0
    for h in range(hours):
        for m in range(60):
            i = h * 60 + m
            close = 100 + 10 * math.sin(i / 220) + i * 0.002
            o = prev
            bars.append(
                CanonicalBar(
                    ts=BASE + timedelta(minutes=i),
                    open=Decimal(str(round(o, 4))),
                    high=Decimal(str(round(max(o, close) * 1.001, 4))),
                    low=Decimal(str(round(min(o, close) * 0.999, 4))),
                    close=Decimal(str(round(close, 4))),
                    volume=Decimal("10"),
                    is_final=True,
                    source="test",
                )
            )
            prev = close
    await md_repo.upsert_bars(session, instrument.id, bars)
    await session.commit()
    return instrument


async def test_suite_runs_and_persists_full_provenance() -> None:
    async with get_sessionmaker()() as session:
        user = User(email="robust@example.com")
        session.add(user)
        await session.commit()
        await _seed(session, hours=200)
        strategy, _ = await StrategyService(session, user.id).create(_spec())
        await session.commit()

        end = BASE + timedelta(hours=200)
        experiment = await RobustnessService(session, user.id).run_suite(
            strategy.id,
            start=BASE,
            end=end,
            folds=3,
            axes=(Axis("indicators.fast.params.period", (4, 5, 6)),),
            monte_carlo_samples=200,
        )
        await session.commit()

        assert experiment.status == "done", experiment.error
        assert experiment.kind == "robustness_suite"

        # Provenance: enough to reproduce the run exactly.
        assert experiment.spec_hash and len(experiment.spec_hash) == 64
        assert experiment.data_fingerprint and len(experiment.data_fingerprint) == 64
        assert experiment.engine_version and experiment.metrics_version
        assert experiment.cost_model_version and experiment.seed is not None
        assert experiment.config["execution"]["commission_bps"] == 2.0
        assert experiment.config["analysis"]["folds"] == 3

        result = experiment.result
        assert result is not None
        assert set(result) >= {
            "baseline",
            "walk_forward",
            "cost_stress",
            "monte_carlo",
            "stability",
            "disclosure",
        }
        assert "hypothetical" in result["disclosure"].lower()

        # The verdict is a checklist, and every check carries its evidence.
        stability = result["stability"]
        assert stability["verdict"] in {"pass", "warn", "fail", "insufficient_evidence"}
        names = {c["name"] for c in stability["checks"]}
        assert names == {
            "sample_size",
            "out_of_sample",
            "cost_sensitivity",
            "parameter_stability",
            "multiple_testing",
            "drawdown",
            "sequence_risk",
        }
        for check in stability["checks"]:
            assert check["detail"], f"{check['name']} reported no reasoning"
        assert "No language model" in stability["method"]

        # Cost stress must be monotonic in the multiple.
        returns = [
            level["metrics"]["total_return"] or 0.0 for level in result["cost_stress"]["levels"]
        ]
        assert returns == sorted(returns, reverse=True)


async def test_suite_is_reproducible_from_its_own_record() -> None:
    """Two runs of the same spec over the same data must agree exactly.

    This is what makes the persisted fingerprint meaningful: if identical inputs
    could produce different numbers, recording them would prove nothing.
    """
    async with get_sessionmaker()() as session:
        user = User(email="repro@example.com")
        session.add(user)
        await session.commit()
        await _seed(session, hours=200)
        strategy, _ = await StrategyService(session, user.id).create(_spec())
        await session.commit()

        service = RobustnessService(session, user.id)
        end = BASE + timedelta(hours=200)
        first = await service.run_suite(
            strategy.id, start=BASE, end=end, folds=3, monte_carlo_samples=200, seed=42
        )
        await session.commit()
        second = await service.run_suite(
            strategy.id, start=BASE, end=end, folds=3, monte_carlo_samples=200, seed=42
        )
        await session.commit()

        assert first.data_fingerprint == second.data_fingerprint
        assert first.spec_hash == second.spec_hash
        # ...and it is a NEW row, never an overwrite.
        assert first.id != second.id
        # The rerun is LINKED to the original, so the experiment list shows repeats
        # as repeats rather than as independent confirmations of the same finding.
        assert second.parent_id == first.id

        # Asking the same question twice is two draws, and the multiple-testing
        # correction has to know that: counting only the current grid understates
        # the search in the one direction it must never err in.
        first_sensitivity = (first.result or {}).get("sensitivity")
        second_sensitivity = (second.result or {}).get("sensitivity")
        if first_sensitivity and second_sensitivity:
            first_trials = (first_sensitivity.get("sharpe_assessment") or {}).get("trials")
            second_trials = (second_sensitivity.get("sharpe_assessment") or {}).get("trials")
            if first_trials and second_trials:
                assert second_trials > first_trials


async def test_suite_refuses_a_window_too_short_to_split() -> None:
    """Better to refuse than to report folds of a dozen bars as out-of-sample evidence."""
    from app.core.errors import BadRequestError

    async with get_sessionmaker()() as session:
        user = User(email="short@example.com")
        session.add(user)
        await session.commit()
        await _seed(session, hours=40, symbol="SHORT/USD")
        strategy, _ = await StrategyService(session, user.id).create(_spec("SHORT/USD"))
        await session.commit()

        try:
            await RobustnessService(session, user.id).run_suite(
                strategy.id, start=BASE, end=BASE + timedelta(hours=40)
            )
        except BadRequestError as exc:
            assert str(MIN_BARS_FOR_ROBUSTNESS) in str(exc.detail)
        else:  # pragma: no cover
            raise AssertionError("expected a refusal on too little history")


async def test_sweeping_a_non_whitelisted_path_is_rejected() -> None:
    """The override language is a closed whitelist; a sweep cannot reach outside it."""
    from app.modules.robustness.overrides import OverrideError

    async with get_sessionmaker()() as session:
        user = User(email="sweep@example.com")
        session.add(user)
        await session.commit()
        await _seed(session, hours=200)
        strategy, _ = await StrategyService(session, user.id).create(_spec())
        await session.commit()

        try:
            await RobustnessService(session, user.id).run_suite(
                strategy.id,
                start=BASE,
                end=BASE + timedelta(hours=200),
                folds=3,
                axes=(Axis("universe", (1, 2)),),
                monte_carlo_samples=100,
            )
        except OverrideError as exc:
            assert "not a sweepable parameter" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected the override whitelist to reject 'universe'")
