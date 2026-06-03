"""AI request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.modules.strategies.spec import StrategySpec


class GenerateStrategyRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class GenerateStrategyResponse(BaseModel):
    spec: StrategySpec  # validated; NOT persisted — the user reviews then saves/backtests
    provider: str


class ExplainRequest(BaseModel):
    context: dict[str, Any]


class ExplainResponse(BaseModel):
    text: str
    provider: str
