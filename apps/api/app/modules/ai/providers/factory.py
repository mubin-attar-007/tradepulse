"""Pick the configured LLM provider (default: Gemini)."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.ai.providers.base import LLMProvider
from app.modules.ai.providers.gemini import GeminiProvider
from app.modules.ai.providers.ollama import OllamaProvider


def make_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.ai_default_provider
    if provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url)
    raise AppError(f"Unsupported AI provider: {provider!r}")
