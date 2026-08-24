"""The research graph's state.

One typed state object flows through every node. Nodes only ever ADD to it, and a
node that cannot do its job records why rather than raising — so a run that stops
early still carries a complete account of how far it got and what blocked it. A
graph that fails by throwing loses exactly the information a user needs.

``stage_log`` is the product's trace: an ordered, sanitized record of what ran,
what it decided, and how long it took. It carries no prompts, no credentials, and
no hidden reasoning — only observable, structured decisions.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, TypedDict

Stage = Literal[
    "classify",
    "extract",
    "clarify",
    "generate",
    "validate",
    "plan",
    "await_approval",
    "experiment",
    "report",
    "done",
    "blocked",
]


class StageRecord(TypedDict):
    """One node's execution, as it will appear in the trace viewer."""

    stage: str
    status: str  # ok | skipped | blocked | error
    detail: str
    duration_ms: float
    # Structured facts only: counts, hashes, verdicts. Never prompt text.
    data: dict[str, Any]


class ResearchState(TypedDict, total=False):
    # --- request identity ----------------------------------------------------
    request_id: str
    owner_id: uuid.UUID
    user_request: str

    # --- what we understood --------------------------------------------------
    intent_label: str
    hypothesis: str
    clarification_answers: dict[str, str]
    ambiguities: list[str]
    unsupported: list[str]

    # --- the proposal --------------------------------------------------------
    spec: dict[str, Any] | None
    spec_hash: str
    applied_defaults: list[str]
    semantic_issues: list[dict[str, str]]
    generation_trace: dict[str, Any]

    # --- the plan and its gate ----------------------------------------------
    plan: dict[str, Any] | None
    plan_hash: str
    data_fingerprint: str
    approval_token: str
    approval_granted: bool

    # --- results -------------------------------------------------------------
    experiment_id: str
    evidence: dict[str, Any]
    report: dict[str, Any]

    # --- control -------------------------------------------------------------
    stage: Stage
    stage_log: list[StageRecord]
    blocked_reason: str
    # Bounded loops: every counter here has a hard ceiling, and reaching it is
    # reported rather than hidden behind a silently truncated result.
    clarification_rounds: int
    repair_rounds: int


def new_state(*, request_id: str, owner_id: uuid.UUID, user_request: str) -> ResearchState:
    return ResearchState(
        request_id=request_id,
        owner_id=owner_id,
        user_request=user_request,
        stage="classify",
        stage_log=[],
        ambiguities=[],
        unsupported=[],
        applied_defaults=[],
        semantic_issues=[],
        clarification_answers={},
        clarification_rounds=0,
        repair_rounds=0,
        approval_granted=False,
    )


def record(
    state: ResearchState,
    stage: str,
    status: str,
    detail: str,
    duration_ms: float = 0.0,
    **data: Any,
) -> None:
    state.setdefault("stage_log", []).append(
        StageRecord(
            stage=stage,
            status=status,
            detail=detail,
            duration_ms=round(duration_ms, 2),
            data=data,
        )
    )
