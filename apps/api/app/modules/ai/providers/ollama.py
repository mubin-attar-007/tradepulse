"""Ollama provider — the default local path.

Ollama is the reference local runtime, but the wire format here is also what
llama.cpp's server and LM Studio speak, so an operator is not locked to one tool.
The model is passed per call rather than baked in at construction: the v1 provider
hardcoded ``llama3.1`` and the factory never passed a model, so whatever the
operator had actually pulled was ignored and every call asked for a model that was
probably not installed.

Errors are CLASSIFIED rather than collapsed. "Model not found" is
``UNAVAILABLE`` (fixable by pulling it, and worth falling back from); a refused
connection is ``UNAVAILABLE`` (Ollama is not running); a timeout is ``TIMEOUT``.
That distinction is what lets the router fall back instead of failing the request.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.modules.ai.providers.base import ErrorKind, LLMResponse, ProviderError


class OllamaProvider:
    name = "ollama"
    local = True

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")

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
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        body: dict[str, Any] = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if json_mode:
            # Ollama constrains sampling to valid JSON. It does not enforce OUR
            # schema, which is why the caller still validates and repairs.
            body["format"] = "json"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ErrorKind.TIMEOUT,
                f"Ollama did not respond within {timeout_seconds:.0f}s. Local models on CPU "
                "are slow; try a smaller profile or raise the timeout.",
                provider=self.name,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                ErrorKind.UNAVAILABLE,
                f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?",
                provider=self.name,
            ) from exc

        if response.status_code == 404:
            raise ProviderError(
                ErrorKind.UNAVAILABLE,
                f"Ollama has no model named {model!r}. Pull it first: `ollama pull {model}`.",
                provider=self.name,
                status=404,
            )
        if response.status_code >= 400:
            raise ProviderError(
                ErrorKind.UNAVAILABLE,
                f"Ollama returned {response.status_code}: {response.text[:200]}",
                provider=self.name,
                status=response.status_code,
            )

        data = response.json()
        return LLMResponse(
            text=data.get("response", ""),
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
            model=model,
            provider=self.name,
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=str(data.get("done_reason", "stop")),
            meta={"eval_duration_ns": data.get("eval_duration")},
        )

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def installed_models(self) -> list[str]:
        """Models actually available locally.

        Used by the readiness surface so an operator can see "the profile asks for
        qwen2.5:3b-instruct and you have not pulled it" instead of discovering it
        as a failed request.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            if response.status_code != 200:
                return []
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []
