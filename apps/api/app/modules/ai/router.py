"""AI endpoints (auth-gated, budget-enforced).

Guardrails: /strategy returns a *validated* spec but never persists or executes
it — the user reviews, then saves (/strategies) or backtests. No endpoint here
can place an order. Every response carries the non-advice framing in its text.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.deps import RedisDep
from app.modules.ai import schemas
from app.modules.ai.providers.factory import make_llm_provider
from app.modules.ai.service import AIService
from app.modules.auth.deps import CurrentUser

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/strategy", response_model=schemas.GenerateStrategyResponse)
async def generate_strategy(
    payload: schemas.GenerateStrategyRequest, redis: RedisDep, user: CurrentUser
) -> schemas.GenerateStrategyResponse:
    provider = make_llm_provider(get_settings())
    spec = await AIService(provider, redis).generate_strategy(payload.prompt, user.id)
    return schemas.GenerateStrategyResponse(spec=spec, provider=provider.name)


@router.post("/explain", response_model=schemas.ExplainResponse)
async def explain_backtest(
    payload: schemas.ExplainRequest, redis: RedisDep, user: CurrentUser
) -> schemas.ExplainResponse:
    provider = make_llm_provider(get_settings())
    text = await AIService(provider, redis).explain_backtest(payload.context, user.id)
    return schemas.ExplainResponse(text=text, provider=provider.name)
