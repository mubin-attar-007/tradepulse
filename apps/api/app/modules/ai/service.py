"""The AI service: natural language in, a validated StrategySpec and a full trace out.

The pipeline, and why each stage exists:

    request
      -> deterministic extraction        what the user demonstrably asked for
      -> unsupported check               refuse BEFORE spending a model call
      -> model produces the IR           compact, id-free, ~5x cheaper than a spec
      -> schema validation               Pydantic; malformed JSON never gets further
      -> semantic verification           did it keep EMA-20/50 and cross_above?
      -> compile to StrategySpec         the DSL's own rules apply, unchanged
      -> repair (bounded, max 2)         structured errors only, never latitude
      -> record the run                  prompt version, provider, tokens, latency

The stage the v1 pipeline lacked entirely is semantic verification. It validated
that output was schema-VALID, which is silent about whether it was the strategy the
user described: a request for a 20/50 EMA cross answered with a 10/30 SMA cross is
perfectly valid JSON and completely wrong, and nothing noticed.

Nothing here executes anything. The service returns a spec for a human to review,
save, and backtest. There is no code path from this module to an order.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.errors import AppError, BadRequestError
from app.core.logging import get_logger
from app.modules.ai import budget, compiler, prompts
from app.modules.ai.circuit import get_breaker
from app.modules.ai.ir import CompileError, StrategyIntent, compile_intent
from app.modules.ai.providers.base import Capability, ProviderError
from app.modules.ai.providers.registry import NoProviderAvailable, ProviderRouter, RoutingStep
from app.modules.strategies.spec import StrategySpec

logger = get_logger("ai")

MAX_REPAIRS = 2
_STRUCTURED = frozenset({Capability.TEXT, Capability.STRUCTURED_OUTPUT})


def strip_fences(text: str) -> str:
    """Recover JSON from a model that wrapped it in a code fence anyway.

    Every prompt says not to, and every model does it sometimes. Failing the request
    over punctuation would be pedantry; the schema validation immediately after is
    what actually decides whether the content is acceptable.
    """
    t = text.strip()
    if t.startswith("```"):
        t = t[3:]
        if t[:4].lower() == "json":
            t = t[4:]
        if t.endswith("```"):
            t = t[:-3]
    t = t.strip()
    # Some models emit a sentence before the object; take the outermost braces.
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            t = t[start : end + 1]
    return t.strip()


@dataclass
class Attempt:
    """One model call, kept whether it succeeded or not.

    Failed attempts are the interesting ones for evaluation, so they are recorded
    rather than discarded on the way to a retry.
    """

    index: int
    profile: str
    provider: str
    model: str
    prompt_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    status: str  # ok | invalid_json | schema_error | compile_error | provider_error
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "profile": self.profile,
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt_id,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": round(self.latency_ms, 2),
            "status": self.status,
            "error": self.error[:400],
        }


@dataclass
class GenerationResult:
    """Everything the caller and the trace viewer need."""

    spec: StrategySpec | None
    intent: StrategyIntent | None
    applied_defaults: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    semantic_issues: list[dict[str, str]] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    routing: list[RoutingStep] = field(default_factory=list)
    status: str = "ok"  # ok | refused | needs_clarification | failed
    message: str = ""
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    deterministic_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "spec": self.spec.model_dump(mode="json") if self.spec else None,
            "spec_hash": self.spec.spec_hash() if self.spec else None,
            "applied_defaults": self.applied_defaults,
            "ambiguities": self.ambiguities,
            "unsupported": self.unsupported,
            "semantic_issues": self.semantic_issues,
            "attempts": [a.as_dict() for a in self.attempts],
            "routing": [s.as_dict() for s in self.routing],
            "total_tokens": self.total_tokens,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "deterministic_only": self.deterministic_only,
            "repairs": max(0, len(self.attempts) - 1),
        }


class AIService:
    def __init__(
        self,
        redis: Redis,
        settings: Settings | None = None,
        router: ProviderRouter | None = None,
    ) -> None:
        self.redis = redis
        self.settings = settings or get_settings()
        self.router = router or ProviderRouter(self.settings, get_breaker())

    async def generate_strategy(
        self,
        request: str,
        user_id: uuid.UUID,
        *,
        max_repairs: int | None = None,
        profile_override: str | None = None,
    ) -> GenerationResult:
        max_repairs = self.settings.ai_max_repairs if max_repairs is None else max_repairs
        extraction = compiler.extract(request)

        # Refuse before spending a model call. An unsupported request does not become
        # supported by asking a model about it, and answering with a nearby strategy
        # the user did not ask for is worse than saying no.
        if extraction.intent.unsupported:
            return GenerationResult(
                spec=None,
                intent=extraction.intent,
                unsupported=extraction.intent.unsupported,
                ambiguities=extraction.intent.ambiguities,
                status="refused",
                message=(
                    "This request asks for something the platform does not do: "
                    + "; ".join(extraction.intent.unsupported)
                    + ". Rephrase it as rules over closed bars on one instrument and it "
                    "can be simulated."
                ),
            )

        # A request that is too vague to contain a rule is a QUESTION, not a failure.
        # Measured on the evaluation set: without this, "buy on strong momentum" ran
        # the model, produced an IR with no entry rule, failed to compile, burned two
        # slow repairs, and came back "could not produce a valid strategy" — while the
        # extractor had already identified precisely what was missing and could have
        # said so instantly and for free.
        if extraction.intent.ambiguities and not extraction.intent.entry:
            return GenerationResult(
                spec=None,
                intent=extraction.intent,
                ambiguities=extraction.intent.ambiguities,
                status="needs_clarification",
                message=(
                    "This needs a bit more detail before it can be simulated: "
                    + "; ".join(extraction.intent.ambiguities)
                ),
            )

        await budget.check(self.redis, user_id, self.settings)

        result = GenerationResult(spec=None, intent=None)
        # Carry the extractor's findings from the start, so a run that fails later
        # still reports what it understood rather than only that it gave up.
        result.ambiguities = list(extraction.intent.ambiguities)
        errors = ""
        previous = ""

        for attempt_index in range(max_repairs + 1):
            prompt_def = prompts.STRATEGY_IR if attempt_index == 0 else prompts.REPAIR
            body = (
                prompts.build_strategy_prompt(request)
                if attempt_index == 0
                else prompts.build_repair_prompt(request, previous, errors)
            )

            started = time.perf_counter()
            try:
                routed = await self.router.generate(
                    system=prompt_def.system,
                    prompt=body,
                    needs=_STRUCTURED,
                    json_mode=True,
                    temperature=prompt_def.temperature,
                    max_tokens=self.settings.ai_max_tokens_per_request,
                    profile_override=profile_override,
                )
            except NoProviderAvailable as exc:
                result.routing = exc.steps
                result.status = "failed"
                result.message = str(exc)
                return result
            except ProviderError as exc:  # pragma: no cover - router normally absorbs these
                result.status = "failed"
                result.message = str(exc)
                return result

            response = routed.response
            result.routing = routed.steps
            result.total_tokens += response.total_tokens
            result.total_latency_ms += response.latency_ms
            result.deterministic_only = bool(response.meta.get("deterministic"))
            await budget.record(self.redis, user_id, response.total_tokens, self.settings)

            attempt = Attempt(
                index=attempt_index,
                profile=routed.profile.name,
                provider=response.provider,
                model=response.model,
                prompt_id=prompt_def.id,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                latency_ms=(time.perf_counter() - started) * 1000,
                status="ok",
            )

            previous = response.text
            try:
                payload = json.loads(strip_fences(response.text))
            except json.JSONDecodeError as exc:
                attempt.status, attempt.error = "invalid_json", str(exc)
                errors = f"The response was not valid JSON: {exc}"
                result.attempts.append(attempt)
                continue

            try:
                intent = StrategyIntent.model_validate(payload)
            except ValidationError as exc:
                attempt.status, attempt.error = "schema_error", str(exc)[:400]
                errors = _format_validation_errors(exc)
                result.attempts.append(attempt)
                continue

            try:
                spec, applied = compile_intent(intent)
            except CompileError as exc:
                attempt.status, attempt.error = "compile_error", str(exc)
                errors = f"The strategy could not be compiled: {exc}"
                result.attempts.append(attempt)
                continue

            result.attempts.append(attempt)
            issues = compiler.verify(request, intent)
            result.spec = spec
            result.intent = intent
            result.applied_defaults = applied
            result.ambiguities = sorted(
                set(extraction.intent.ambiguities) | set(intent.ambiguities)
            )
            result.unsupported = list(intent.unsupported)
            result.semantic_issues = [i.as_dict() for i in issues]
            result.status = "ok"
            if issues:
                # Do NOT silently correct it. The user sees the spec AND what it
                # failed to honour, and decides — a checker that quietly rewrites
                # model output hides the very failure it was built to expose.
                result.message = (
                    f"The generated strategy does not match {len(issues)} thing(s) the "
                    "request asked for. Review the highlighted differences before saving."
                )
            elif result.ambiguities:
                result.message = (
                    "Generated with assumptions where the request was open. Review them "
                    "before saving."
                )
            logger.info(
                "ai_strategy_generated",
                profile=routed.profile.name,
                repairs=attempt_index,
                semantic_issues=len(issues),
                tokens=result.total_tokens,
            )
            return result

        result.status = "failed"
        # State the limit explicitly. "It failed" and "it ran out of the attempts it
        # was allowed" call for different actions from the user, and hiding which one
        # happened makes the bound feel arbitrary.
        result.message = (
            f"Could not produce a valid strategy within the {max_repairs} repair "
            f"attempt(s) allowed (AI_MAX_REPAIRS). Last problem: {errors[:300]}"
        )
        logger.info("ai_strategy_failed", attempts=len(result.attempts))
        return result

    async def explain(
        self, evidence: dict[str, Any], user_id: uuid.UUID
    ) -> tuple[str, dict[str, Any]]:
        """Narrate a result using only the supplied numbers.

        ``evidence`` must be assembled by the CALLER from a persisted experiment, not
        accepted from the client. The v1 endpoint took an arbitrary dict from the
        request body, so anyone could have the model narrate numbers of their own
        invention and the output was described as "grounded".
        """
        await budget.check(self.redis, user_id, self.settings)
        try:
            routed = await self.router.generate(
                system=prompts.NARRATION.system,
                prompt=prompts.build_narration_prompt(evidence),
                needs=frozenset({Capability.TEXT}),
                json_mode=False,
                max_tokens=self.settings.ai_max_tokens_per_request,
            )
        except NoProviderAvailable as exc:
            raise AppError(str(exc)) from exc

        await budget.record(self.redis, user_id, routed.response.total_tokens, self.settings)
        text = routed.response.text.strip()

        from app.modules.ai.grounding import check_grounding

        grounding = check_grounding(text, evidence)
        return text, {
            "profile": routed.profile.name,
            "provider": routed.response.provider,
            "model": routed.response.model,
            "prompt": prompts.NARRATION.id,
            "tokens": routed.response.total_tokens,
            "latency_ms": round(routed.response.latency_ms, 2),
            "routing": [s.as_dict() for s in routed.steps],
            "grounding": grounding.as_dict(),
        }


def _format_validation_errors(exc: ValidationError) -> str:
    """Compact, actionable errors for the repair prompt.

    Pydantic's full output is long and repeats the input; a model given all of it
    tends to rewrite everything. Location plus message keeps the repair narrow.
    """
    lines = []
    for error in exc.errors()[:8]:
        location = ".".join(str(p) for p in error["loc"])
        lines.append(f"- {location or '(root)'}: {error['msg']}")
    return "\n".join(lines)


def require_spec(result: GenerationResult) -> StrategySpec:
    """Unwrap a successful generation or raise the appropriate 4xx."""
    if result.spec is None:
        raise BadRequestError(result.message or "Could not generate a strategy.")
    return result.spec
