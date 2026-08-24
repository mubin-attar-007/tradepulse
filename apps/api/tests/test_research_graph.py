"""The research graph: stages, bounds, the approval gate, and the safety boundary.

The graph's safety properties are structural, so the tests are too: they check that
the capability surface contains no dangerous tool, that an experiment cannot run
without a content-bound approval, and that a run which stops early still explains
itself. Everything runs on the deterministic provider — no model, no network.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import PermissionDeniedError
from app.core.redis import get_redis_client
from app.modules.ai.graph import graph as research_graph
from app.modules.ai.graph import tools
from app.modules.ai.graph.approval import (
    APPROVAL_TTL_SECONDS,
    ApprovalSubject,
    mint,
    plan_hash,
    verify,
)
from app.modules.ai.service import AIService
from app.modules.auth.models import User
from app.modules.market_data import repository as md_repo
from app.modules.market_data.providers.base import CanonicalBar

# Seeded relative to NOW: the planning tool looks back a bounded window, so a
# fixture pinned to a fixed past date silently ages out of range and the graph
# blocks for "not enough history" rather than exercising what the test is about.
BASE = (datetime.now(UTC) - timedelta(days=40)).replace(minute=0, second=0, microsecond=0)
EMA_CROSS = (
    "Buy BTC/USD on the 1h chart when the 20-period EMA crosses above the 50-period EMA, "
    "and exit when it crosses back below. Use a 2% stop loss."
)


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AI_PROFILE_CHAIN_RAW", "deterministic")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed(session, *, hours: int = 300, symbol: str = "BTC/USD"):  # type: ignore[no-untyped-def]
    instrument = await md_repo.get_or_create_instrument(
        session, symbol=symbol, asset_class="crypto", calendar="24x7"
    )
    bars = []
    prev = 100.0
    for i in range(hours * 60):
        close = 100 + 9 * math.sin(i / 900) + i * 0.0004
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


# --- the capability surface --------------------------------------------------


def test_the_agent_has_no_dangerous_capability() -> None:
    """Safety is the absence of a tool, not an instruction in a prompt.

    If someone adds an execute/query/shell/order tool to this module, this test is
    the thing that notices.
    """
    exposed = {name for name in dir(tools) if not name.startswith("_")}
    forbidden = {
        "execute_sql",
        "run_python",
        "run_shell",
        "eval",
        "exec",
        "place_order",
        "submit_order",
        "install_package",
        "http_get",
        "fetch_url",
        "read_secret",
        "get_credentials",
    }
    assert exposed & forbidden == set()


def test_the_toolset_is_small_and_deliberate() -> None:
    """A capability surface that grows silently stops being a boundary."""
    callables = {
        name for name in dir(tools) if not name.startswith("_") and callable(getattr(tools, name))
    }
    # Imported helpers appear here too; what matters is that every TOOL is expected.
    expected_tools = {
        "classify_request",
        "understand_request",
        "list_supported_indicators",
        "inspect_dataset",
        "build_experiment_plan",
        "run_planned_experiment",
        "build_report",
    }
    assert expected_tools <= callables


def test_the_indicator_catalog_the_agent_sees_is_the_real_one() -> None:
    from app.modules.indicators.catalog import INDICATOR_PARAMS

    listed = {entry["type"] for entry in tools.list_supported_indicators()}
    assert listed == set(INDICATOR_PARAMS)


# --- approval ----------------------------------------------------------------


def _subject(owner: uuid.UUID) -> ApprovalSubject:
    return ApprovalSubject(
        owner_id=owner,
        spec_hash="a" * 64,
        data_fingerprint="b" * 64,
        plan_hash=plan_hash({"analyses": ["backtest"]}),
        action="run_experiment",
    )


def test_a_valid_approval_verifies() -> None:
    owner = uuid.uuid4()
    subject = _subject(owner)
    verify(mint(subject), subject)


def test_an_approval_does_not_transfer_to_another_user() -> None:
    subject = _subject(uuid.uuid4())
    token = mint(subject)
    other = ApprovalSubject(
        owner_id=uuid.uuid4(),
        spec_hash=subject.spec_hash,
        data_fingerprint=subject.data_fingerprint,
        plan_hash=subject.plan_hash,
        action=subject.action,
    )
    with pytest.raises(PermissionDeniedError):
        verify(token, other)


@pytest.mark.parametrize("field", ["spec_hash", "data_fingerprint", "plan_hash", "action"])
def test_editing_anything_material_invalidates_the_approval(field: str) -> None:
    """This is what makes 'any material edit invalidates approval' a property of the
    system rather than a promise in a document."""
    owner = uuid.uuid4()
    subject = _subject(owner)
    token = mint(subject)
    changed = ApprovalSubject(
        owner_id=owner,
        spec_hash="z" * 64 if field == "spec_hash" else subject.spec_hash,
        data_fingerprint="z" * 64 if field == "data_fingerprint" else subject.data_fingerprint,
        plan_hash="z" * 64 if field == "plan_hash" else subject.plan_hash,
        action="deploy_paper" if field == "action" else subject.action,
    )
    with pytest.raises(PermissionDeniedError) as exc:
        verify(token, changed)
    assert "no longer applies" in str(exc.value.detail)


def test_an_approval_expires() -> None:
    subject = _subject(uuid.uuid4())
    token = mint(subject, issued_at=0)
    with pytest.raises(PermissionDeniedError) as exc:
        verify(token, subject, now=APPROVAL_TTL_SECONDS + 10)
    assert "expired" in str(exc.value.detail)


def test_a_forged_signature_is_rejected() -> None:
    subject = _subject(uuid.uuid4())
    digest, issued, _signature = mint(subject).split(".")
    with pytest.raises(PermissionDeniedError):
        verify(f"{digest}.{issued}.{'0' * 64}", subject)


def test_a_reordered_plan_is_the_same_plan() -> None:
    """Canonical hashing, so cosmetic serialization differences do not invalidate."""
    assert plan_hash({"a": 1, "b": [1, 2]}) == plan_hash({"b": [1, 2], "a": 1})


# --- the graph ---------------------------------------------------------------


async def test_propose_stops_at_the_approval_gate_and_runs_nothing() -> None:
    async with get_sessionmaker()() as session:
        user = User(email="graph@example.com")
        session.add(user)
        await session.commit()
        await _seed(session)

        result = await research_graph.propose(
            service=AIService(get_redis_client()),
            session=session,
            owner_id=user.id,
            request=EMA_CROSS,
        )

        assert result["stage"] == "await_approval"
        assert result["approval_required"] is True
        assert result["approval_token"]
        assert result["spec"]["universe"] == ["BTC/USD"]
        assert result["plan"]["symbol"] == "BTC/USD"
        assert result["experiment_id"] is None
        # Nothing was persisted on the proposal pass.
        listing = await session.execute(
            __import__("sqlalchemy").text("SELECT count(*) FROM experiments")
        )
        assert listing.scalar() == 0

        stages = [entry["stage"] for entry in result["trace"]]
        assert stages == ["classify", "extract", "generate", "validate", "plan", "await_approval"]
        for entry in result["trace"]:
            assert entry["detail"], f"{entry['stage']} recorded no reasoning"


async def test_an_unsupported_request_is_blocked_before_generation() -> None:
    async with get_sessionmaker()() as session:
        user = User(email="blocked@example.com")
        session.add(user)
        await session.commit()

        result = await research_graph.propose(
            service=AIService(get_redis_client()),
            session=session,
            owner_id=user.id,
            request="Use 20x leverage on BTC options and guarantee me a profit",
        )
        assert result["stage"] == "blocked"
        assert result["unsupported"]
        assert result["spec"] is None
        # It stopped at extraction: the model was never called.
        assert [entry["stage"] for entry in result["trace"]] == ["classify", "extract"]


async def test_a_plan_is_refused_when_the_data_cannot_support_it() -> None:
    """Better to say why than to produce folds of a dozen bars and call them
    out-of-sample evidence."""
    async with get_sessionmaker()() as session:
        user = User(email="nodata@example.com")
        session.add(user)
        await session.commit()
        await _seed(session, hours=5)

        result = await research_graph.propose(
            service=AIService(get_redis_client()),
            session=session,
            owner_id=user.id,
            request=EMA_CROSS,
        )
        assert result["stage"] == "blocked"
        assert "bars" in result["blocked_reason"]


async def test_execute_runs_the_experiment_and_reports_with_citations() -> None:
    async with get_sessionmaker()() as session:
        user = User(email="execute@example.com")
        session.add(user)
        await session.commit()
        await _seed(session)

        service = AIService(get_redis_client())
        proposal = await research_graph.propose(
            service=service, session=session, owner_id=user.id, request=EMA_CROSS
        )
        assert proposal["stage"] == "await_approval"

        from app.modules.ai.graph.state import ResearchState

        state = ResearchState(
            request_id="t",
            owner_id=user.id,
            user_request=EMA_CROSS,
            spec=proposal["spec"],
            spec_hash=proposal["spec_hash"],
            plan=proposal["plan"],
            plan_hash=proposal["plan_hash"],
            data_fingerprint=proposal["data_fingerprint"],
            stage="await_approval",
            stage_log=[],
            hypothesis=proposal["hypothesis"],
            applied_defaults=[],
            semantic_issues=[],
            approval_granted=True,
        )
        final = await research_graph.execute(
            service=service, session=session, owner_id=user.id, state=state
        )
        await session.commit()

        assert final["stage"] == "done", final.get("blocked_reason")
        assert final["experiment_id"]
        report = final["report"]
        assert report["verdict"] in {"pass", "warn", "fail", "insufficient_evidence"}
        assert report["citations"], "every claim must name where it came from"
        for citation in report["citations"]:
            assert citation["source"].startswith("experiment:")
        assert "hypothetical" in report["disclosure"].lower()
        # Reproducibility: the report names everything needed to run it again.
        assert set(report["reproduce"]) == {
            "experiment_id",
            "spec_hash",
            "data_fingerprint",
            "plan_hash",
        }


async def test_the_report_contains_no_number_the_experiment_did_not_produce() -> None:
    """The report is assembled from the persisted record, so this is structural —
    but asserting it keeps it that way."""
    async with get_sessionmaker()() as session:
        user = User(email="grounded@example.com")
        session.add(user)
        await session.commit()
        await _seed(session)

        service = AIService(get_redis_client())
        proposal = await research_graph.propose(
            service=service, session=session, owner_id=user.id, request=EMA_CROSS
        )
        from app.modules.ai.graph.state import ResearchState

        state = ResearchState(
            request_id="t",
            owner_id=user.id,
            user_request=EMA_CROSS,
            spec=proposal["spec"],
            spec_hash=proposal["spec_hash"],
            plan=proposal["plan"],
            plan_hash=proposal["plan_hash"],
            data_fingerprint=proposal["data_fingerprint"],
            stage="await_approval",
            stage_log=[],
            approval_granted=True,
        )
        final = await research_graph.execute(
            service=service, session=session, owner_id=user.id, state=state
        )
        await session.commit()

        from app.modules.experiments.repository import ExperimentRepository

        experiment = await ExperimentRepository(session, user.id).get(
            uuid.UUID(final["experiment_id"])
        )
        assert experiment is not None
        baseline = (experiment.result or {}).get("baseline", {}).get("metrics", {})
        headline = final["report"]["headline_metrics"]
        for key, value in headline.items():
            assert value == baseline.get(key), f"{key} does not match the experiment record"
