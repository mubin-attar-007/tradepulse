"""AI service: NL -> validated StrategySpec (never auto-executed) and grounded
backtest narration. Token usage is budgeted per user + globally.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.errors import BadRequestError
from app.core.logging import get_logger
from app.modules.ai import budget, prompts
from app.modules.ai.providers.base import LLMProvider
from app.modules.strategies.spec import StrategySpec

logger = get_logger("ai")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t[3:]
        if t[:4].lower() == "json":
            t = t[4:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


class AIService:
    def __init__(self, provider: LLMProvider, redis: Redis) -> None:
        self.provider = provider
        self.redis = redis

    async def generate_strategy(
        self, nl: str, user_id: uuid.UUID, *, max_repairs: int = 2
    ) -> StrategySpec:
        """Validate-and-repair loop. Returns a validated spec; NEVER executes it."""
        await budget.check(self.redis, user_id)
        errors: str | None = None
        last_output: str | None = None
        for attempt in range(max_repairs + 1):
            prompt = prompts.build_strategy_prompt(nl, errors, last_output)
            resp = await self.provider.generate(
                system=prompts.STRATEGY_SYSTEM, prompt=prompt, json_mode=True
            )
            await budget.record(self.redis, user_id, resp.total_tokens)
            try:
                data = json.loads(_strip_fences(resp.text))
                return StrategySpec.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                errors = str(exc)[:2000]
                last_output = resp.text[:4000]
                logger.info("ai_strategy_repair", attempt=attempt + 1)
        raise BadRequestError("Could not produce a valid strategy from that prompt; rephrase it.")

    async def explain_backtest(self, context: dict[str, Any], user_id: uuid.UUID) -> str:
        """Plain-English narration grounded in the provided numbers only."""
        await budget.check(self.redis, user_id)
        resp = await self.provider.generate(
            system=prompts.NARRATION_SYSTEM,
            prompt=prompts.build_explain_prompt(context),
            json_mode=False,
        )
        await budget.record(self.redis, user_id, resp.total_tokens)
        return resp.text.strip()
