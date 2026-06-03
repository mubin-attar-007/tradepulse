"""AI layer: NL->StrategySpec validate/repair, budget, guardrails (hermetic)."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient

from app.core.errors import BadRequestError, RateLimitedError
from app.core.redis import get_redis_client
from app.modules.ai import budget
from app.modules.ai.providers.base import LLMResponse
from app.modules.ai.service import AIService
from app.modules.strategies.spec import example_composite_spec

_VALID = json.dumps(example_composite_spec().model_dump(mode="json"))


class FakeProvider:
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.2
    ) -> LLMResponse:
        text = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return LLMResponse(text=text, tokens_in=10, tokens_out=20, model="fake", provider="fake")


async def test_generate_strategy_valid() -> None:
    service = AIService(FakeProvider([_VALID]), get_redis_client())
    spec = await service.generate_strategy("buy dips", uuid.uuid4())
    assert spec.name == example_composite_spec().name


async def test_generate_strategy_repairs() -> None:
    fake = FakeProvider(["not json at all", _VALID])
    spec = await AIService(fake, get_redis_client()).generate_strategy("x", uuid.uuid4())
    assert spec.name and fake.calls == 2


async def test_generate_strategy_gives_up() -> None:
    service = AIService(FakeProvider(["definitely not json"]), get_redis_client())
    with pytest.raises(BadRequestError):
        await service.generate_strategy("x", uuid.uuid4(), max_repairs=1)


async def test_generate_strategy_strips_code_fences() -> None:
    fenced = f"```json\n{_VALID}\n```"
    spec = await AIService(FakeProvider([fenced]), get_redis_client()).generate_strategy(
        "x", uuid.uuid4()
    )
    assert spec.name == example_composite_spec().name


async def test_budget_blocks_when_exceeded() -> None:
    redis = get_redis_client()
    user_id = uuid.uuid4()
    await budget.record(redis, user_id, budget.DAILY_USER_TOKENS)
    with pytest.raises(RateLimitedError):
        await budget.check(redis, user_id)


async def test_explain_returns_grounded_text() -> None:
    provider = FakeProvider(["Negative Sharpe over a tiny sample. This is not financial advice."])
    text = await AIService(provider, get_redis_client()).explain_backtest(
        {"sharpe": -12.2, "num_trades": 12}, uuid.uuid4()
    )
    assert "not financial advice" in text.lower()


# --- endpoint ---
async def _login(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "ai@example.com", "password": "password123"})


async def test_ai_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/ai/strategy", json={"prompt": "hello"})).status_code == 401


async def test_ai_strategy_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.ai.router as ai_router

    monkeypatch.setattr(ai_router, "make_llm_provider", lambda settings: FakeProvider([_VALID]))
    await _login(client)
    resp = await client.post("/ai/strategy", json={"prompt": "buy when oversold"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "fake"
    assert body["spec"]["name"] == example_composite_spec().name
