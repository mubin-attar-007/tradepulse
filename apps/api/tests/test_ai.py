"""AI endpoints: auth gating, response contract, and the narration anchor.

Unit-level behaviour of the compiler, router and grounding checks lives in
``test_ai_compiler.py`` and ``test_ai_service.py``; this file covers the HTTP
surface — that the endpoints are gated, that the response carries the trace a
reviewer needs, and that narration cannot be pointed at numbers the caller made up.

These run against the deterministic provider, so no key and no model are needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.experiments.models import Experiment
from tests.conftest import authenticate

EMA_CROSS = (
    "Buy BTC/USD on the 1h chart when the 20-period EMA crosses above the 50-period EMA, "
    "and exit when it crosses back below. Use a 2% stop loss and risk 1% of equity per trade."
)


@pytest.fixture(autouse=True)
def _deterministic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the provider chain so these tests never touch a network or a model."""
    monkeypatch.setenv("AI_PROFILE_CHAIN_RAW", "deterministic")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- gating ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/ai/strategy", {"prompt": "hello there"}),
        ("post", "/ai/clarify", {"prompt": "hello there"}),
        ("post", "/ai/explain", {"experiment_id": str(uuid.uuid4())}),
        ("get", "/ai/status", None),
    ],
)
async def test_every_ai_endpoint_requires_auth(
    client: AsyncClient, method: str, path: str, body: dict | None
) -> None:
    response = await getattr(client, method)(path, **({"json": body} if body else {}))
    assert response.status_code == 401


# --- generation --------------------------------------------------------------


async def test_strategy_endpoint_returns_a_spec_and_its_trace(client: AsyncClient) -> None:
    await authenticate(client, "ai@example.com")
    response = await client.post("/ai/strategy", json={"prompt": EMA_CROSS})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "ok"
    assert body["spec"]["universe"] == ["BTC/USD"]
    assert body["spec"]["timeframe"] == "1h"
    assert len(body["spec_hash"]) == 64
    assert body["semantic_issues"] == []
    assert body["repairs"] == 0
    # The trace is part of the contract: a reviewer must be able to see which
    # profile answered, under which prompt version, and what it cost.
    assert body["attempts"][0]["prompt"].startswith("strategy_ir@")
    assert body["routing"][-1]["outcome"] == "selected"
    # Rule-based output must never be presented as model output.
    assert body["deterministic_only"] is True


async def test_the_generated_spec_is_not_persisted(client: AsyncClient) -> None:
    """The AI proposes; a human decides. Generation must not create a strategy."""
    await authenticate(client, "nosave@example.com")
    await client.post("/ai/strategy", json={"prompt": EMA_CROSS})
    listing = await client.get("/strategies")
    assert listing.status_code == 200
    assert listing.json() == []


async def test_an_unsupported_request_is_refused_with_a_reason(client: AsyncClient) -> None:
    await authenticate(client, "refuse@example.com")
    response = await client.post(
        "/ai/strategy",
        json={"prompt": "Give me a guaranteed profitable strategy using 10x leverage on options"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused"
    assert body["spec"] is None
    assert body["unsupported"]
    assert "does not do" in body["message"]


async def test_an_unknown_profile_is_rejected(client: AsyncClient) -> None:
    await authenticate(client, "profile@example.com")
    response = await client.post(
        "/ai/strategy", json={"prompt": EMA_CROSS, "profile": "gpt-9-ultra"}
    )
    assert response.status_code == 400


# --- clarify -----------------------------------------------------------------


async def test_clarify_reports_understanding_without_calling_a_model(
    client: AsyncClient,
) -> None:
    await authenticate(client, "clarify@example.com")
    response = await client.post(
        "/ai/clarify", json={"prompt": "Buy on strong momentum with a tight stop"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ambiguities"], "vague phrasing should be surfaced, not guessed at"
    assert body["understood"]["symbol"] is None


async def test_clarify_echoes_the_constraints_it_will_hold_a_model_to(
    client: AsyncClient,
) -> None:
    await authenticate(client, "constraints@example.com")
    response = await client.post("/ai/clarify", json={"prompt": EMA_CROSS})
    body = response.json()
    kinds = {c["kind"] for c in body["constraints"]}
    assert {"indicator", "period", "operator", "timeframe", "symbol", "stop"} <= kinds


# --- narration ---------------------------------------------------------------


async def _experiment_for(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    """A completed experiment owned by ``email``, for the narration tests."""
    async with get_sessionmaker()() as session:
        user = User(email=email)
        session.add(user)
        await session.commit()
        experiment = Experiment(
            owner_id=user.id,
            kind="robustness_suite",
            status="done",
            title="Fixture run",
            symbol="BTC/USD",
            timeframe="1h",
            bars=500,
            engine_version="0.1.0",
            metrics_version="2.0.0",
            cost_model_version="1.0.0",
            data_fingerprint="f" * 64,
            spec_hash="a" * 64,
            completed_at=datetime.now(UTC),
            config={"execution": {"commission_bps": 2.0, "slippage_bps": 1.0}},
            result={
                "baseline": {"metrics": {"total_return": 0.0374, "max_drawdown": -0.152}},
                "stability": {"verdict": "warn", "checks": []},
            },
        )
        session.add(experiment)
        await session.commit()
        return user.id, experiment.id


async def test_explain_is_anchored_to_a_persisted_experiment(client: AsyncClient) -> None:
    """The v1 endpoint narrated an arbitrary dict from the request body, so anyone
    could have the model describe invented numbers while the output was called
    grounded. Narration now names an experiment the caller owns."""
    _user_id, experiment_id = await _experiment_for("explain@example.com")
    # A different signed-in user must not be able to read it.
    await authenticate(client, "other@example.com")
    response = await client.post("/ai/explain", json={"experiment_id": str(experiment_id)})
    assert response.status_code == 404


async def test_explain_rejects_an_unfinished_experiment(client: AsyncClient) -> None:
    await authenticate(client, "pending@example.com")
    me = (await client.get("/auth/me")).json()
    async with get_sessionmaker()() as session:
        experiment = Experiment(
            owner_id=uuid.UUID(me["id"]),
            kind="robustness_suite",
            status="running",
            title="Still going",
        )
        session.add(experiment)
        await session.commit()
        experiment_id = experiment.id

    response = await client.post("/ai/explain", json={"experiment_id": str(experiment_id)})
    assert response.status_code == 400
    assert "no result" in response.json()["detail"]


# --- status ------------------------------------------------------------------


async def test_status_explains_what_the_ai_layer_can_actually_do(client: AsyncClient) -> None:
    """The baseline failure was invisible: an expired key produced a 500 per request
    with no way to see the provider chain was empty."""
    await authenticate(client, "status@example.com")
    response = await client.get("/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert body["chain"] == ["deterministic"]
    assert any(p["name"] == "local-balanced" for p in body["profiles"])
    assert any("deterministic" in note for note in body["notes"])
    for profile in body["profiles"]:
        assert profile["circuit_state"] in {"closed", "open", "half_open"}
