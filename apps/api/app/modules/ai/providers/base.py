"""The LLM provider contract. Concrete providers (Gemini, Ollama) normalize to
this so the AI service is provider-agnostic and the budget tracker sees uniform
token usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.2
    ) -> LLMResponse: ...
