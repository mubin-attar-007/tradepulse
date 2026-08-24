"""OpenAI-compatible chat-completions provider.

One adapter covers every runtime that speaks this wire format: llama.cpp's server,
LM Studio, vLLM, Groq, OpenRouter, Together, and OpenAI itself. That is why it
exists instead of a per-vendor adapter — the platform gains all of them for the cost
of maintaining one, and an operator chooses by setting a base URL.

Locality is a CONFIGURATION fact here, not a property of the code: a llama.cpp
server on localhost is local, Groq is not. The caller declares which, and the router
enforces the local-only policy against that declaration.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.modules.ai.providers.base import ErrorKind, LLMResponse, ProviderError


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str = "", *, local: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.local = local

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout_seconds: float = 120.0,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ErrorKind.TIMEOUT, f"{self.base_url} timed out.", provider=self.name
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                ErrorKind.UNAVAILABLE,
                f"Could not reach {self.base_url}: {exc}",
                provider=self.name,
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderError(
                ErrorKind.AUTHENTICATION,
                f"{self.base_url} rejected the credential.",
                provider=self.name,
                status=response.status_code,
            )
        if response.status_code == 429:
            raise ProviderError(
                ErrorKind.RATE_LIMIT, "Rate limited.", provider=self.name, status=429
            )
        if response.status_code >= 400:
            raise ProviderError(
                ErrorKind.UNAVAILABLE,
                f"{self.base_url} returned {response.status_code}: {response.text[:200]}",
                provider=self.name,
                status=response.status_code,
            )

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return LLMResponse(
            text=(choice.get("message") or {}).get("content", "") or "",
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=model,
            provider=self.name,
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=str(choice.get("finish_reason", "stop")),
        )

    async def healthy(self) -> bool:
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/models", headers=headers)
            return response.status_code < 400
        except Exception:
            return False
