"""AI endpoints (auth-gated, budget-enforced).

Guardrails that hold structurally rather than by convention:

* ``/ai/strategy`` returns a validated spec and NEVER persists or executes it. The
  user reviews it, then saves it via ``/strategies`` and backtests it deliberately.
* ``/ai/explain`` narrates a PERSISTED experiment the caller owns. It cannot be
  handed arbitrary numbers to describe — that was the v1 shape, and it made the
  word "grounded" meaningless.
* No endpoint in this module can reach an order. Live execution is gated elsewhere
  and answers 403 by construction; there is no path from here to it at all.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.deps import RedisDep, SessionDep
from app.core.errors import BadRequestError, NotFoundError
from app.modules.ai import compiler, schemas
from app.modules.ai.circuit import get_breaker
from app.modules.ai.providers.ollama import OllamaProvider
from app.modules.ai.providers.registry import ALL_PROFILES, configured_chain, resolve_profile
from app.modules.ai.service import AIService
from app.modules.auth.deps import CurrentUser
from app.modules.experiments.repository import ExperimentRepository

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/strategy", response_model=schemas.GenerateStrategyResponse)
async def generate_strategy(
    payload: schemas.GenerateStrategyRequest, redis: RedisDep, user: CurrentUser
) -> schemas.GenerateStrategyResponse:
    """Natural language -> a validated StrategySpec, with the full trace."""
    if payload.profile and payload.profile not in ALL_PROFILES:
        raise BadRequestError(
            f"Unknown model profile {payload.profile!r}. Known: {sorted(ALL_PROFILES)}"
        )
    service = AIService(redis)
    result = await service.generate_strategy(
        payload.prompt, user.id, profile_override=payload.profile
    )
    return schemas.GenerateStrategyResponse.model_validate(result.as_dict())


@router.post("/clarify", response_model=schemas.ClarifyResponse)
async def clarify(payload: schemas.ClarifyRequest, _user: CurrentUser) -> schemas.ClarifyResponse:
    """What the platform understands from a request — with no model call.

    Instant and free, so a user can see how their wording will be read before
    spending a slow local generation on it. It is the same extraction the semantic
    checker later holds the model to, which is why it is worth exposing.
    """
    extraction = compiler.extract(payload.prompt)
    intent = extraction.intent
    return schemas.ClarifyResponse(
        understood={
            "symbol": intent.symbol,
            "timeframe": intent.timeframe,
            "entry_rules": [rule.signature() for rule in intent.entry],
            "exit_rules": [rule.signature() for rule in intent.exit.rules],
            "stop_loss_pct": intent.exit.stop_loss_pct,
            "take_profit_pct": intent.exit.take_profit_pct,
            "trailing_stop_pct": intent.exit.trailing_stop_pct,
            "sizing": intent.sizing.model_dump(mode="json"),
        },
        ambiguities=intent.ambiguities,
        unsupported=intent.unsupported,
        constraints=[
            {"kind": c.kind, "detail": c.detail, "evidence": c.evidence}
            for c in extraction.constraints
        ],
    )


@router.post("/explain", response_model=schemas.ExplainResponse)
async def explain_experiment(
    payload: schemas.ExplainRequest,
    session: SessionDep,
    redis: RedisDep,
    user: CurrentUser,
) -> schemas.ExplainResponse:
    """Explain a stored experiment using only the numbers it actually contains."""
    experiment = await ExperimentRepository(session, user.id).get(payload.experiment_id)
    if experiment is None:
        raise NotFoundError()
    if experiment.status != "done" or not experiment.result:
        raise BadRequestError("That experiment has no result to explain.")

    # The evidence payload is assembled HERE, from the persisted record, so the set
    # of numbers the model may cite is exactly the set the grounding check verifies.
    result = experiment.result
    evidence = {
        "strategy": experiment.title,
        "symbol": experiment.symbol,
        "timeframe": experiment.timeframe,
        "bars": experiment.bars,
        "engine_version": experiment.engine_version,
        "cost_model": (experiment.config or {}).get("execution"),
        "baseline": result.get("baseline"),
        "walk_forward": {
            k: v
            for k, v in (result.get("walk_forward") or {}).items()
            if k in {"oos_total_return", "consistency", "oos_positive_folds", "degradation"}
        },
        "cost_stress": {
            "breakeven_multiple": (result.get("cost_stress") or {}).get("breakeven_multiple")
        },
        "stability": {
            "verdict": (result.get("stability") or {}).get("verdict"),
            "checks": [
                {"name": c.get("name"), "verdict": c.get("verdict")}
                for c in (result.get("stability") or {}).get("checks", [])
            ],
        },
    }
    text, meta = await AIService(redis).explain(evidence, user.id)
    return schemas.ExplainResponse(text=text, **meta)


@router.get("/status", response_model=schemas.AIStatusOut)
async def ai_status(_user: CurrentUser) -> schemas.AIStatusOut:
    """What the AI layer can do right now, and why a profile is unavailable."""
    settings = get_settings()
    breaker = get_breaker()
    chain = [p.name for p in configured_chain(settings)]

    installed: list[str] = []
    if any(ALL_PROFILES[name].provider == "ollama" for name in chain if name in ALL_PROFILES):
        installed = await OllamaProvider(settings.ollama_base_url).installed_models()

    profiles: list[schemas.ProfileOut] = []
    notes: list[str] = []
    for name in ALL_PROFILES:
        profile = resolve_profile(name, settings)
        configured = name in chain
        profiles.append(
            schemas.ProfileOut(
                name=profile.name,
                provider=profile.provider,
                model=profile.model,
                local=profile.local,
                capabilities=sorted(c.value for c in profile.capabilities),
                context_tokens=profile.context_tokens,
                description=profile.description,
                configured=configured,
                circuit_state=str(breaker.state(profile.name)),
            )
        )
        if (
            configured
            and profile.provider == "ollama"
            and installed
            and profile.model not in installed
        ):
            notes.append(
                f"Profile '{profile.name}' wants {profile.model!r}, which is not pulled. "
                f"Run: ollama pull {profile.model}"
            )
    if settings.ai_local_only:
        notes.append("AI_LOCAL_ONLY is on: no request may leave this machine.")
    if chain == ["deterministic"]:
        notes.append(
            "No model provider is configured, so requests are served by the deterministic "
            "rule-based compiler. It is not a language model, and output is labelled as such."
        )
    return schemas.AIStatusOut(
        local_only=settings.ai_local_only,
        chain=chain,
        profiles=profiles,
        installed_local_models=installed,
        notes=notes,
    )
