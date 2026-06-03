"""Local Ollama provider (zero marginal cost; optional fallback)."""

from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.providers.base import LLMResponse


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.2
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            body["format"] = "json"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
        return LLMResponse(
            text=data.get("response", ""),
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
            model=self.model,
            provider="ollama",
        )
