"""Research-copilot endpoints.

Two calls, deliberately:

    POST /research/propose   -> understand, generate, validate, plan. Runs NOTHING.
    POST /research/execute   -> verify the approval token, then run the experiment.

Splitting them is what makes the approval gate real. A single call with an
``approved: true`` flag would be a checkbox the client controls; here the second
call must present a token that was minted over the exact strategy, dataset, plan and
risk-policy version shown in the first — so an edited strategy, a re-backfilled
dataset, or a changed plan all invalidate it automatically.

It also means a restart cannot lose an approval, because the token IS the approval
rather than a pointer to in-memory graph state.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import RedisDep, SessionDep
from app.core.errors import BadRequestError
from app.modules.ai.graph import graph as research_graph
from app.modules.ai.graph.approval import ApprovalSubject, verify
from app.modules.ai.graph.state import ResearchState
from app.modules.ai.service import AIService
from app.modules.auth.deps import CurrentUser
from app.modules.strategies.spec import StrategySpec

router = APIRouter(prefix="/research", tags=["research-copilot"])


class ProposeRequest(BaseModel):
    request: str = Field(min_length=3, max_length=2000)


class ExecuteRequest(BaseModel):
    """Everything needed to resume an approved run.

    The client returns the proposal it was shown. Nothing is trusted: the token is
    verified against hashes recomputed from these fields, so a client that edits the
    spec or the plan before approving simply fails verification.
    """

    request: str = Field(min_length=3, max_length=2000)
    spec: StrategySpec
    plan: dict = Field(default_factory=dict)
    data_fingerprint: str = Field(min_length=1, max_length=64)
    approval_token: str = Field(min_length=1, max_length=256)


@router.post("/propose")
async def propose(
    payload: ProposeRequest, session: SessionDep, redis: RedisDep, user: CurrentUser
) -> dict:
    """Understand the request, propose a strategy, and plan an experiment.

    Runs no experiment and saves no strategy. The response carries the plan, every
    assumption applied, every disagreement between the request and the proposal, and
    an approval token for exactly this proposal.
    """
    result = await research_graph.propose(
        service=AIService(redis),
        session=session,
        owner_id=user.id,
        request=payload.request,
    )
    return result


@router.post("/execute")
async def execute(
    payload: ExecuteRequest, session: SessionDep, redis: RedisDep, user: CurrentUser
) -> dict:
    """Run an approved plan and return the report.

    The approval is re-derived from the submitted content, so it cannot be reused
    for a different strategy, a different dataset, or a different plan.
    """
    from app.modules.ai.graph.approval import plan_hash

    subject = ApprovalSubject(
        owner_id=user.id,
        spec_hash=payload.spec.spec_hash(),
        data_fingerprint=payload.data_fingerprint,
        plan_hash=plan_hash(payload.plan),
        action="run_experiment",
    )
    verify(payload.approval_token, subject)  # raises 403 with the reason

    if not payload.plan:
        raise BadRequestError("An approved plan is required to run an experiment.")

    state: ResearchState = ResearchState(
        request_id=uuid.uuid4().hex,
        owner_id=user.id,
        user_request=payload.request,
        spec=payload.spec.model_dump(mode="json"),
        spec_hash=payload.spec.spec_hash(),
        plan=payload.plan,
        plan_hash=subject.plan_hash,
        data_fingerprint=payload.data_fingerprint,
        stage="await_approval",
        stage_log=[],
        ambiguities=[],
        unsupported=[],
        applied_defaults=[],
        semantic_issues=[],
        clarification_answers={},
        clarification_rounds=0,
        repair_rounds=0,
        approval_granted=True,
    )
    return await research_graph.execute(
        service=AIService(redis), session=session, owner_id=user.id, state=state
    )
