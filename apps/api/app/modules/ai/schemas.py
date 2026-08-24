"""AI request/response schemas.

The response is deliberately wide. A strategy that arrives with no indication of
what was assumed, what the request left ambiguous, or where the model disagreed
with the request is a strategy the user cannot review — and reviewing it is the
entire point, because nothing here is ever executed automatically.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.modules.strategies.spec import StrategySpec


class GenerateStrategyRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    # Named profile ('local-small', 'local-balanced', 'remote-fast', 'deterministic').
    # Lets a user trade latency for quality explicitly instead of guessing.
    profile: str | None = Field(default=None, max_length=40)


class AttemptOut(BaseModel):
    index: int
    profile: str
    provider: str
    model: str
    prompt: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    status: str
    error: str


class RoutingStepOut(BaseModel):
    profile: str
    provider: str
    outcome: str
    reason: str


class SemanticIssueOut(BaseModel):
    """A place the generated strategy departs from the request.

    Surfaced rather than auto-corrected: the user decides whether the model or their
    own wording was wrong, and a checker that silently rewrites output hides exactly
    the failure it exists to expose.
    """

    kind: str
    expected: str
    evidence: str
    problem: str


class GenerateStrategyResponse(BaseModel):
    status: str  # ok | refused | failed
    message: str
    # Validated but NOT persisted and NOT executed: the user reviews, then saves.
    spec: StrategySpec | None
    spec_hash: str | None
    applied_defaults: list[str]
    ambiguities: list[str]
    unsupported: list[str]
    semantic_issues: list[SemanticIssueOut]
    attempts: list[AttemptOut]
    routing: list[RoutingStepOut]
    repairs: int
    total_tokens: int
    total_latency_ms: float
    # True when the output came from the deterministic compiler rather than a model.
    # The UI must label it as such; presenting rule-based output as AI output would
    # be a lie about the system's own behaviour.
    deterministic_only: bool


class ExplainRequest(BaseModel):
    """Narration is anchored to a PERSISTED experiment, never to client-supplied numbers.

    The v1 endpoint accepted an arbitrary context dict from the request body, so any
    caller could have the model narrate figures of their own invention while the
    output was described as grounded.
    """

    experiment_id: uuid.UUID


class GroundingOut(BaseModel):
    ok: bool
    supported_numbers: list[str]
    unsupported_numbers: list[str]
    causal_claims: list[str]
    predictive_claims: list[str]
    has_disclosure: bool
    method: str


class ExplainResponse(BaseModel):
    text: str
    profile: str
    provider: str
    model: str
    prompt: str
    tokens: int
    latency_ms: float
    routing: list[RoutingStepOut]
    # Every number in `text` checked against the experiment it narrates.
    grounding: GroundingOut


class ProfileOut(BaseModel):
    name: str
    provider: str
    model: str
    local: bool
    capabilities: list[str]
    context_tokens: int
    description: str
    configured: bool
    circuit_state: str


class AIStatusOut(BaseModel):
    """What the AI layer can actually do right now.

    Exists because the baseline failure mode was invisible: an expired key produced
    a 500 on every request with no way to see that the provider chain was empty.
    """

    local_only: bool
    chain: list[str]
    profiles: list[ProfileOut]
    installed_local_models: list[str]
    notes: list[str]


class ClarifyRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class ClarifyResponse(BaseModel):
    """Deterministic pre-flight: what is unclear, unsupported, or already understood.

    Runs with no model call at all, so it is instant and free, and it is the same
    extraction the semantic checker later verifies the model against.
    """

    understood: dict[str, Any]
    ambiguities: list[str]
    unsupported: list[str]
    constraints: list[dict[str, str]]
