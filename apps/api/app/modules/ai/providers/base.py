"""The model-provider contract.

The v1 contract was a single ``generate()`` method and a provider name. That is
enough to call a model and nothing else — it cannot express what a provider is good
at, whether it is currently healthy, what a call cost, or whether sending this
particular text to it is allowed. Every one of those turned into a product problem:
an invalid API key surfaced as a 500, there was no fallback to the local model, and
research prompts left the machine by default with no disclosure.

So the contract carries:

* **Capabilities** — what a provider can actually be trusted to do. Structured
  output is the one that matters: a model that cannot reliably emit constrained JSON
  should never be routed a strategy-generation request, however cheap it is.
* **Locality** — whether a call leaves the machine. This is a policy input, not a
  performance note: with ``AI_LOCAL_ONLY`` set, remote providers are not merely
  deprioritised, they are unreachable.
* **Health** — every call updates a circuit breaker, so a dead provider stops being
  retried instead of turning each request into a timeout.
* **Measurement** — tokens, latency and finish reason on every response, so an AI
  run can be recorded and evaluated rather than merely performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Capability(StrEnum):
    """What a caller needs, not what a provider advertises."""

    TEXT = "text"
    # Constrained JSON that validates against a supplied schema. A provider claims
    # this only if it has a real JSON mode; "usually returns JSON" is not this.
    STRUCTURED_OUTPUT = "structured_output"
    LONG_CONTEXT = "long_context"  # >= 32k tokens
    EMBEDDING = "embedding"


class ErrorKind(StrEnum):
    """Why a call failed — the distinction that decides whether to retry.

    Retrying a permanent authentication failure is how a misconfiguration becomes a
    rate-limit ban; retrying a timeout is how a transient blip becomes invisible.
    The v1 provider collapsed all of these into one generic error, so neither
    decision could be made.
    """

    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"  # permanent until a human fixes it
    RATE_LIMIT = "rate_limit"
    INVALID_OUTPUT = "invalid_output"  # returned text that would not validate
    CONTEXT_OVERFLOW = "context_overflow"
    UNAVAILABLE = "unavailable"  # connection refused, 5xx, model not pulled
    POLICY_BLOCKED = "policy_blocked"  # provider refused on its own safety grounds
    UNKNOWN = "unknown"

    @property
    def is_retryable(self) -> bool:
        return self in {
            ErrorKind.TIMEOUT,
            ErrorKind.RATE_LIMIT,
            ErrorKind.UNAVAILABLE,
            ErrorKind.INVALID_OUTPUT,
        }

    @property
    def is_permanent(self) -> bool:
        """Failures no amount of retrying will fix."""
        return self in {ErrorKind.AUTHENTICATION, ErrorKind.CONTEXT_OVERFLOW}


class ProviderError(Exception):
    """A classified provider failure."""

    def __init__(
        self, kind: ErrorKind, message: str, *, provider: str = "", status: int | None = None
    ):
        self.kind = kind
        self.provider = provider
        self.status = status
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """A named, portable description of a model the platform can route to.

    Profiles are referred to by NAME (``local-small``, ``local-quality``) everywhere
    in the application, so no prompt, node, or config names a vendor. Swapping the
    model behind a profile is then a config change rather than a code change — and,
    importantly, an evaluation can report which profile produced a result without
    leaking a vendor into the schema.
    """

    name: str
    provider: str  # 'fake' | 'ollama' | 'openai_compatible' | 'gemini'
    model: str
    capabilities: frozenset[Capability]
    context_tokens: int
    local: bool
    description: str = ""
    # Rough guidance for the router, measured on the operator's own hardware rather
    # than taken from a vendor claim. None when never measured.
    observed_tokens_per_second: float | None = None

    def supports(self, needed: Capability) -> bool:
        return needed in self.capabilities


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    # Free-form provider detail, kept for the trace. Never contains credentials.
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@runtime_checkable
class LLMProvider(Protocol):
    """Every provider normalizes to this, so the service is provider-agnostic."""

    name: str
    local: bool

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
    ) -> LLMResponse: ...

    async def healthy(self) -> bool:
        """Cheap liveness probe. Must not raise."""
        ...
