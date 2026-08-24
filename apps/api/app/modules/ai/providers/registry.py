"""Model profiles, provider construction, and capability-aware routing.

The v1 factory was ``if provider == "gemini": return GeminiProvider(...)``. With one
configured provider and no health signal, an expired key took the entire AI feature
down and there was nothing to fall back to.

The router replaces that with an explicit, inspectable decision:

1. Start from the profiles the operator has configured, in preference order.
2. Drop any that cannot do what the CALLER needs (structured output, context size).
3. Drop remote profiles entirely when the local-only policy is on — this is a
   policy gate, not a preference, because it governs whether the user's research
   text leaves the machine.
4. Drop any whose circuit breaker is open.
5. Try the survivors in order, and record WHY each was skipped or failed.

That last part is the point: every routing decision is returned alongside the
result, so "the AI is slow today" has an answer in the trace rather than in a log
somewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.core.config import Settings
from app.modules.ai.circuit import CircuitBreaker, CircuitState
from app.modules.ai.providers.base import (
    Capability,
    ErrorKind,
    LLMProvider,
    LLMResponse,
    ModelProfile,
    ProviderError,
)
from app.modules.ai.providers.fake import FAKE_PROFILE, FakeProvider
from app.modules.ai.providers.gemini import GeminiProvider
from app.modules.ai.providers.ollama import OllamaProvider
from app.modules.ai.providers.openai_compatible import OpenAICompatibleProvider

STRUCTURED = frozenset({Capability.TEXT, Capability.STRUCTURED_OUTPUT})

# Local profiles, smallest first. The sizes are chosen for a CPU-only machine,
# because that is what the free local path actually runs on: on the reference
# hardware (6 cores, no usable GPU) a 3B model produced ~2.6 tokens/second, which
# is why the compiler asks the model for a compact IR rather than a full spec.
LOCAL_PROFILES: dict[str, ModelProfile] = {
    "local-small": ModelProfile(
        name="local-small",
        provider="ollama",
        model="qwen2.5:1.5b-instruct",
        capabilities=STRUCTURED,
        context_tokens=32_768,
        local=True,
        description="Fastest local option. Adequate for classification and short IR.",
    ),
    "local-balanced": ModelProfile(
        name="local-balanced",
        provider="ollama",
        model="qwen2.5:3b-instruct",
        capabilities=STRUCTURED,
        context_tokens=32_768,
        local=True,
        description="Default local profile. Apache-2.0 weights, ~2 GB, CPU-viable.",
    ),
    "local-quality": ModelProfile(
        name="local-quality",
        provider="ollama",
        model="qwen2.5:7b-instruct",
        capabilities=STRUCTURED | {Capability.LONG_CONTEXT},
        context_tokens=32_768,
        local=True,
        description="Best local quality; noticeably slow without a GPU.",
    ),
}

REMOTE_PROFILES: dict[str, ModelProfile] = {
    "remote-fast": ModelProfile(
        name="remote-fast",
        provider="gemini",
        model="gemini-2.0-flash",
        capabilities=STRUCTURED | {Capability.LONG_CONTEXT},
        context_tokens=1_000_000,
        local=False,
        description="Hosted. Sends the request to Google; requires an API key.",
    ),
    "remote-compatible": ModelProfile(
        name="remote-compatible",
        provider="openai_compatible",
        model="",  # supplied by AI_OPENAI_MODEL
        capabilities=STRUCTURED,
        context_tokens=128_000,
        local=False,
        description="Any OpenAI-compatible endpoint (vLLM, Groq, OpenRouter, LM Studio).",
    ),
}

ALL_PROFILES: dict[str, ModelProfile] = {
    FAKE_PROFILE.name: FAKE_PROFILE,
    **LOCAL_PROFILES,
    **REMOTE_PROFILES,
}


@dataclass(frozen=True, slots=True)
class RoutingStep:
    """One profile the router considered, and what happened."""

    profile: str
    provider: str
    outcome: str  # selected | skipped | failed
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {
            "profile": self.profile,
            "provider": self.provider,
            "outcome": self.outcome,
            "reason": self.reason,
        }


@dataclass
class RoutingResult:
    response: LLMResponse
    profile: ModelProfile
    steps: list[RoutingStep] = field(default_factory=list)
    attempts: int = 1


class NoProviderAvailable(Exception):
    """Nothing could serve the request. Carries the full decision trail."""

    def __init__(self, message: str, steps: list[RoutingStep]) -> None:
        self.steps = steps
        super().__init__(message)


def build_provider(profile: ModelProfile, settings: Settings) -> LLMProvider:
    if profile.provider == "fake":
        return FakeProvider()
    if profile.provider == "ollama":
        return OllamaProvider(settings.ollama_base_url)
    if profile.provider == "gemini":
        return GeminiProvider(settings.gemini_api_key)
    if profile.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            settings.ai_openai_base_url,
            settings.ai_openai_api_key,
            local=settings.ai_openai_is_local,
        )
    raise ValueError(f"Unknown provider {profile.provider!r}")


def resolve_profile(name: str, settings: Settings) -> ModelProfile:
    """A profile by name, with operator overrides applied.

    The model behind a profile is configurable so an operator who pulled a different
    local model does not have to edit code — the v1 provider hardcoded a model name
    and ignored whatever was actually installed.
    """
    profile = ALL_PROFILES.get(name)
    if profile is None:
        raise ValueError(f"Unknown model profile {name!r}. Known: {sorted(ALL_PROFILES)}")
    if profile.provider == "ollama" and settings.ollama_model:
        profile = replace(profile, model=settings.ollama_model)
    if profile.provider == "gemini" and settings.gemini_model:
        profile = replace(profile, model=settings.gemini_model)
    if profile.provider == "openai_compatible" and settings.ai_openai_model:
        profile = replace(profile, model=settings.ai_openai_model)
    return profile


def configured_chain(settings: Settings) -> list[ModelProfile]:
    """The profiles to try, in order, given how the operator configured things.

    Deliberately conservative: a profile whose credential is missing is not in the
    chain at all, so it can never contribute a confusing failure.
    """
    chain: list[ModelProfile] = []
    for name in settings.ai_profile_chain:
        try:
            profile = resolve_profile(name.strip(), settings)
        except ValueError:
            continue
        if profile.provider == "gemini" and not settings.gemini_api_key:
            continue
        if profile.provider == "openai_compatible" and not settings.ai_openai_base_url:
            continue
        chain.append(profile)
    if not chain:
        # Never leave the AI surface with nothing to call. The deterministic provider
        # is always available, always labelled, and never presented as a model.
        chain.append(FAKE_PROFILE)
    return chain


class ProviderRouter:
    """Picks a provider per request and records why."""

    def __init__(self, settings: Settings, breaker: CircuitBreaker | None = None) -> None:
        self.settings = settings
        self.breaker = breaker or CircuitBreaker()

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        needs: frozenset[Capability] = frozenset({Capability.TEXT}),
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        profile_override: str | None = None,
    ) -> RoutingResult:
        settings = self.settings
        steps: list[RoutingStep] = []

        if profile_override:
            chain = [resolve_profile(profile_override, settings)]
        else:
            chain = configured_chain(settings)

        attempts = 0
        for profile in chain:
            missing = {cap for cap in needs if not profile.supports(cap)}
            if missing:
                steps.append(
                    RoutingStep(
                        profile.name,
                        profile.provider,
                        "skipped",
                        f"cannot do {sorted(c.value for c in missing)}",
                    )
                )
                continue
            if settings.ai_local_only and not profile.local:
                steps.append(
                    RoutingStep(
                        profile.name,
                        profile.provider,
                        "skipped",
                        "AI_LOCAL_ONLY is set and this profile sends the request off-machine",
                    )
                )
                continue
            state = self.breaker.state(profile.name)
            if state is CircuitState.OPEN:
                steps.append(
                    RoutingStep(
                        profile.name,
                        profile.provider,
                        "skipped",
                        "circuit breaker open after repeated failures",
                    )
                )
                continue

            provider = build_provider(profile, settings)
            attempts += 1
            try:
                response = await provider.generate(
                    system=system,
                    prompt=prompt,
                    model=profile.model,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=settings.ai_timeout_seconds,
                )
            except ProviderError as exc:
                self.breaker.record_failure(profile.name, exc.kind)
                steps.append(
                    RoutingStep(profile.name, profile.provider, "failed", f"{exc.kind}: {exc}")
                )
                if exc.kind is ErrorKind.CONTEXT_OVERFLOW:
                    # A bigger model will not help if we sent too much; stop early
                    # rather than replaying an oversized prompt at every provider.
                    break
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self.breaker.record_failure(profile.name, ErrorKind.UNKNOWN)
                steps.append(
                    RoutingStep(profile.name, profile.provider, "failed", f"unexpected: {exc}")
                )
                continue

            self.breaker.record_success(profile.name)
            steps.append(RoutingStep(profile.name, profile.provider, "selected", "ok"))
            return RoutingResult(response=response, profile=profile, steps=steps, attempts=attempts)

        raise NoProviderAvailable(
            "No configured model profile could serve this request. "
            + "; ".join(f"{s.profile}: {s.reason}" for s in steps),
            steps,
        )
