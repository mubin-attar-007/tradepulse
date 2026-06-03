"""LLM provider adapters (Gemini default, Ollama local fallback)."""

from app.modules.ai.providers.base import LLMProvider, LLMResponse

__all__ = ["LLMProvider", "LLMResponse"]
