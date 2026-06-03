"""Google Gemini provider (via the REST API — no extra SDK dependency)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import AppError, RateLimitedError
from app.modules.ai.providers.base import LLMResponse

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        if not api_key:
            raise AppError("GEMINI_API_KEY is not configured.")
        self._api_key = api_key
        self.model = model

    async def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.2
    ) -> LLMResponse:
        generation: dict[str, Any] = {"temperature": temperature}
        if json_mode:
            generation["responseMimeType"] = "application/json"
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }
        url = f"{_BASE}/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, params={"key": self._api_key}, json=body)
        if resp.status_code == 429:
            raise RateLimitedError("Gemini rate limit / quota reached; try again later.")
        if resp.status_code != 200:
            raise AppError(f"Gemini request failed ({resp.status_code}).")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "no_candidates")
            raise AppError(f"Gemini returned no content ({reason}).")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            tokens_in=int(usage.get("promptTokenCount", 0)),
            tokens_out=int(usage.get("candidatesTokenCount", 0)),
            model=self.model,
            provider="gemini",
        )
