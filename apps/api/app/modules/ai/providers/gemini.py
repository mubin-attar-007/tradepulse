"""Google Gemini provider (REST, no extra SDK dependency).

Remote and therefore OPTIONAL: nothing in the product requires it, and with
``AI_LOCAL_ONLY`` it is unreachable regardless of configuration. It stays because a
hosted model is genuinely faster and stronger than a 3B local one, and the honest
answer is to offer it with the data-egress consequence stated rather than to
pretend the local model is as good.

Error classification matters more here than anywhere else: the baseline audit found
an expired key surfacing as an HTTP 500 with the upstream message discarded, and no
fallback to the local provider. A 400 ``API_KEY_INVALID`` is now permanent (never
retried) and carries the upstream reason, so the operator can act on it.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.modules.ai.providers.base import ErrorKind, LLMResponse, ProviderError

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _classify(response: httpx.Response) -> ErrorKind:
    """Map an upstream status onto a retry decision.

    A 400 from Gemini is most often an invalid key, which is permanent — retrying it
    burns quota and can trip abuse protection. A 429 is genuinely transient.
    """
    if response.status_code == 429:
        return ErrorKind.RATE_LIMIT
    if response.status_code in (401, 403):
        return ErrorKind.AUTHENTICATION
    if response.status_code == 400:
        body = response.text
        if "API_KEY_INVALID" in body or "API key not valid" in body:
            return ErrorKind.AUTHENTICATION
        if "maximum number of tokens" in body or "too long" in body:
            return ErrorKind.CONTEXT_OVERFLOW
        return ErrorKind.UNKNOWN
    if response.status_code >= 500:
        return ErrorKind.UNAVAILABLE
    return ErrorKind.UNKNOWN


def _upstream_reason(response: httpx.Response) -> str:
    """The provider's own message, which the v1 adapter discarded.

    "Gemini request failed (400)" told an operator nothing. "API key not valid"
    tells them exactly what to fix.
    """
    try:
        message = (response.json().get("error") or {}).get("message") or ""
        if message:
            return f"Gemini rejected the request ({response.status_code}): {message}"
    except Exception:
        pass
    return f"Gemini rejected the request ({response.status_code})."


class GeminiProvider:
    name = "gemini"
    local = False

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> LLMResponse:
        if not self._api_key:
            raise ProviderError(
                ErrorKind.AUTHENTICATION,
                "GEMINI_API_KEY is not configured.",
                provider=self.name,
            )
        generation: dict[str, Any] = {"temperature": temperature}
        if json_mode:
            generation["responseMimeType"] = "application/json"
        if max_tokens is not None:
            generation["maxOutputTokens"] = max_tokens
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    f"{_BASE}/{model}:generateContent",
                    params={"key": self._api_key},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(ErrorKind.TIMEOUT, "Gemini timed out.", provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                ErrorKind.UNAVAILABLE, f"Could not reach Gemini: {exc}", provider=self.name
            ) from exc

        if response.status_code != 200:
            raise ProviderError(
                _classify(response),
                _upstream_reason(response),
                provider=self.name,
                status=response.status_code,
            )

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no_candidates")
            raise ProviderError(
                ErrorKind.POLICY_BLOCKED,
                f"Gemini returned no content ({reason}).",
                provider=self.name,
            )
        parts = (candidates[0].get("content") or {}).get("parts") or []
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text="".join(part.get("text", "") for part in parts),
            tokens_in=int(usage.get("promptTokenCount", 0)),
            tokens_out=int(usage.get("candidatesTokenCount", 0)),
            model=model,
            provider=self.name,
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=str(candidates[0].get("finishReason", "STOP")),
        )

    async def healthy(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(_BASE, params={"key": self._api_key})
            return response.status_code == 200
        except Exception:
            return False
