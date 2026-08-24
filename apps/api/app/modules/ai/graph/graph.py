"""The research graph.

One durable graph with explicit stages, deterministic tools, bounded loops and a
human approval gate — not a swarm of agents talking to each other. Every node
either advances the state or records why it could not, so a run that stops early
still explains itself.

    classify -> extract -> generate -> validate -> plan -> await_approval
                                                              |
                                                    (token verified)
                                                              v
                                                       experiment -> report

What the graph is NOT allowed to do, structurally rather than by instruction:

* It cannot execute code, SQL, or shell — its only capabilities are the typed
  functions in :mod:`app.modules.ai.graph.tools`.
* It cannot place an order. There is no order-placing tool, and the live path is
  gated elsewhere and answers 403.
* It cannot run an experiment without a human approval token bound to the exact
  strategy, dataset and plan (:mod:`app.modules.ai.graph.approval`).
* It cannot loop indefinitely: clarification and repair rounds are capped, and
  hitting a cap is reported in the trace rather than silently truncating the work.

The model participates in exactly one stage — turning the request into an IR — and
everything before and after it is deterministic. That is the product principle in
executable form.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.ai.graph import tools
from app.modules.ai.graph.approval import ApprovalSubject, mint, plan_hash
from app.modules.ai.graph.state import ResearchState, new_state, record
from app.modules.ai.service import AIService

logger = get_logger("research_graph")

MAX_CLARIFICATION_ROUNDS = 1
MAX_REPAIR_ROUNDS = 2


def _elapsed(started: float) -> float:
    return (time.perf_counter() - started) * 1000


async def classify_node(state: ResearchState) -> ResearchState:
    """Decide what kind of request this is — deterministically.

    A model call here would be slower, less predictable, and no more accurate for
    the distinction that matters (is this a strategy description, or a request the
    platform refuses?), which the extractor already answers from explicit patterns.
    """
    started = time.perf_counter()
    label, reason = tools.classify_request(state["user_request"])
    state["intent_label"] = label
    record(state, "classify", "ok", reason, _elapsed(started), label=label)
    state["stage"] = "extract"
    return state


async def extract_node(state: ResearchState) -> ResearchState:
    started = time.perf_counter()
    understanding = tools.understand_request(state["user_request"])
    state["ambiguities"] = understanding["ambiguities"]
    state["unsupported"] = understanding["unsupported"]
    state["hypothesis"] = understanding["hypothesis"]

    if understanding["unsupported"]:
        state["stage"] = "blocked"
        state["blocked_reason"] = (
            "The request asks for something the platform does not do: "
            + "; ".join(understanding["unsupported"])
        )
        record(
            state,
            "extract",
            "blocked",
            state["blocked_reason"],
            _elapsed(started),
            unsupported=understanding["unsupported"],
        )
        return state

    record(
        state,
        "extract",
        "ok",
        f"{len(understanding['constraints'])} constraint(s) recognised",
        _elapsed(started),
        constraints=understanding["constraints"],
        ambiguities=understanding["ambiguities"],
    )
    state["stage"] = "clarify" if understanding["ambiguities"] else "generate"
    return state


async def clarify_node(state: ResearchState) -> ResearchState:
    """Ask once, then proceed with stated assumptions.

    An unbounded clarification loop is worse than a stated assumption: it stalls the
    user and produces nothing. One round, then the run continues and every default
    it applied is reported alongside the result.
    """
    started = time.perf_counter()
    answered = set(state.get("clarification_answers", {}))
    outstanding = [a for a in state.get("ambiguities", []) if a not in answered]

    if state.get("clarification_rounds", 0) >= MAX_CLARIFICATION_ROUNDS:
        record(
            state,
            "clarify",
            "skipped",
            f"clarification limit ({MAX_CLARIFICATION_ROUNDS}) reached; continuing with "
            "explicitly stated assumptions",
            _elapsed(started),
            outstanding=outstanding,
        )
    else:
        state["clarification_rounds"] = state.get("clarification_rounds", 0) + 1
        record(
            state,
            "clarify",
            "ok" if not outstanding else "blocked",
            "all questions answered" if not outstanding else f"{len(outstanding)} open question(s)",
            _elapsed(started),
            outstanding=outstanding,
        )
    state["stage"] = "generate"
    return state


def make_generate_node(service: AIService):  # type: ignore[no-untyped-def]
    async def generate_node(state: ResearchState) -> ResearchState:
        started = time.perf_counter()
        result = await service.generate_strategy(
            state["user_request"], state["owner_id"], max_repairs=MAX_REPAIR_ROUNDS
        )
        state["repair_rounds"] = max(0, len(result.attempts) - 1)
        state["generation_trace"] = result.as_dict()
        state["semantic_issues"] = result.semantic_issues
        state["applied_defaults"] = result.applied_defaults

        if result.spec is None:
            state["stage"] = "blocked"
            state["blocked_reason"] = result.message
            record(
                state,
                "generate",
                "blocked",
                result.message,
                _elapsed(started),
                attempts=len(result.attempts),
            )
            return state

        state["spec"] = result.spec.model_dump(mode="json")
        state["spec_hash"] = result.spec.spec_hash()
        record(
            state,
            "generate",
            "ok",
            f"strategy proposed after {state['repair_rounds']} repair(s)",
            _elapsed(started),
            spec_hash=state["spec_hash"][:16],
            profile=(result.attempts[-1].profile if result.attempts else "n/a"),
            deterministic=result.deterministic_only,
            tokens=result.total_tokens,
        )
        state["stage"] = "validate"
        return state

    return generate_node


async def validate_node(state: ResearchState) -> ResearchState:
    """Report disagreement with the request; never silently correct it."""
    started = time.perf_counter()
    issues = state.get("semantic_issues", [])
    record(
        state,
        "validate",
        "ok" if not issues else "blocked",
        "the strategy matches the request"
        if not issues
        else f"{len(issues)} difference(s) from the request — review before running",
        _elapsed(started),
        issues=issues,
    )
    state["stage"] = "plan"
    return state


def make_plan_node(session: AsyncSession):  # type: ignore[no-untyped-def]
    async def plan_node(state: ResearchState) -> ResearchState:
        started = time.perf_counter()
        spec = state.get("spec")
        if spec is None:  # pragma: no cover - guarded by the edge condition
            state["stage"] = "blocked"
            return state

        plan, fingerprint, problem = await tools.build_experiment_plan(session, spec)
        if problem:
            state["stage"] = "blocked"
            state["blocked_reason"] = problem
            record(state, "plan", "blocked", problem, _elapsed(started))
            return state

        state["plan"] = plan
        state["data_fingerprint"] = fingerprint
        state["plan_hash"] = plan_hash(plan)

        subject = ApprovalSubject(
            owner_id=state["owner_id"],
            spec_hash=state["spec_hash"],
            data_fingerprint=fingerprint,
            plan_hash=state["plan_hash"],
            action="run_experiment",
        )
        state["approval_token"] = mint(subject)
        record(
            state,
            "plan",
            "ok",
            f"{plan['analyses']} analyses over {plan['bars']} bars",
            _elapsed(started),
            plan=plan,
            data_fingerprint=fingerprint[:16],
        )
        state["stage"] = "await_approval"
        return state

    return plan_node


async def await_approval_node(state: ResearchState) -> ResearchState:
    """The gate. The graph STOPS here on the proposal pass.

    Nothing expensive and nothing with side effects runs before a human has seen
    the plan and approved this exact strategy over this exact data.
    """
    started = time.perf_counter()
    if not state.get("approval_granted"):
        record(
            state,
            "await_approval",
            "blocked",
            "waiting for human approval of this strategy, dataset and plan",
            _elapsed(started),
            approval_required=True,
        )
        return state
    record(state, "await_approval", "ok", "approved by the requesting user", _elapsed(started))
    state["stage"] = "experiment"
    return state


def make_experiment_node(session: AsyncSession):  # type: ignore[no-untyped-def]
    async def experiment_node(state: ResearchState) -> ResearchState:
        started = time.perf_counter()
        plan = state.get("plan") or {}
        experiment_id, evidence, problem = await tools.run_planned_experiment(
            session, owner_id=state["owner_id"], spec=state["spec"], plan=plan
        )
        if problem:
            state["stage"] = "blocked"
            state["blocked_reason"] = problem
            record(state, "experiment", "error", problem, _elapsed(started))
            return state

        state["experiment_id"] = experiment_id
        state["evidence"] = evidence
        record(
            state,
            "experiment",
            "ok",
            f"experiment {experiment_id[:8]} completed",
            _elapsed(started),
            experiment_id=experiment_id,
            verdict=(evidence.get("stability") or {}).get("verdict"),
        )
        state["stage"] = "report"
        return state

    return experiment_node


async def report_node(state: ResearchState) -> ResearchState:
    """Assemble a report from the experiment's own numbers.

    Deterministic on purpose. Narration by a model is available separately through
    ``/ai/explain``, where it is grounded against this same evidence and every
    number it produces is checked. The report itself never depends on a model.
    """
    started = time.perf_counter()
    state["report"] = tools.build_report(dict(state))
    record(
        state,
        "report",
        "ok",
        "report assembled from the experiment record",
        _elapsed(started),
        citations=len(state["report"].get("citations", [])),
    )
    state["stage"] = "done"
    return state


def _after_extract(state: ResearchState) -> str:
    if state["stage"] == "blocked":
        return "blocked"
    return "clarify" if state["stage"] == "clarify" else "generate"


def _after_generate(state: ResearchState) -> str:
    return "blocked" if state["stage"] == "blocked" else "validate"


def _after_plan(state: ResearchState) -> str:
    return "blocked" if state["stage"] == "blocked" else "await_approval"


def _after_approval(state: ResearchState) -> str:
    return "experiment" if state.get("approval_granted") else "halt"


def _after_experiment(state: ResearchState) -> str:
    return "blocked" if state["stage"] == "blocked" else "report"


def build_graph(service: AIService, session: AsyncSession):  # type: ignore[no-untyped-def]
    """Compile the graph. Nodes are bound to their dependencies here, so the graph
    definition itself stays free of I/O concerns."""
    builder: StateGraph = StateGraph(ResearchState)
    builder.add_node("classify", classify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("generate", make_generate_node(service))
    builder.add_node("validate", validate_node)
    builder.add_node("plan", make_plan_node(session))
    builder.add_node("await_approval", await_approval_node)
    builder.add_node("experiment", make_experiment_node(session))
    builder.add_node("report", report_node)

    builder.set_entry_point("classify")
    builder.add_edge("classify", "extract")
    builder.add_conditional_edges(
        "extract", _after_extract, {"clarify": "clarify", "generate": "generate", "blocked": END}
    )
    builder.add_edge("clarify", "generate")
    builder.add_conditional_edges(
        "generate", _after_generate, {"validate": "validate", "blocked": END}
    )
    builder.add_edge("validate", "plan")
    builder.add_conditional_edges(
        "plan", _after_plan, {"await_approval": "await_approval", "blocked": END}
    )
    builder.add_conditional_edges(
        "await_approval", _after_approval, {"experiment": "experiment", "halt": END}
    )
    builder.add_conditional_edges(
        "experiment", _after_experiment, {"report": "report", "blocked": END}
    )
    builder.add_edge("report", END)
    return builder.compile()


async def propose(
    *,
    service: AIService,
    session: AsyncSession,
    owner_id: uuid.UUID,
    request: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Run the graph up to the approval gate. Nothing is executed."""
    graph = build_graph(service, session)
    state = new_state(
        request_id=request_id or uuid.uuid4().hex,
        owner_id=owner_id,
        user_request=request,
    )
    final: ResearchState = await graph.ainvoke(state)
    return _serialize(final)


async def execute(
    *,
    service: AIService,
    session: AsyncSession,
    owner_id: uuid.UUID,
    state: ResearchState,
) -> dict[str, Any]:
    """Continue an APPROVED run from the gate onward."""
    graph = build_graph(service, session)
    state["approval_granted"] = True
    state["stage"] = "await_approval"
    final: ResearchState = await graph.ainvoke(state)
    return _serialize(final)


def _serialize(state: ResearchState) -> dict[str, Any]:
    """The state, minus anything a client has no business seeing.

    The user request itself is echoed (the client sent it), but no prompt text, no
    provider credential and no model reasoning ever appears here.
    """
    return {
        "request_id": state.get("request_id"),
        "stage": state.get("stage"),
        "intent": state.get("intent_label"),
        "hypothesis": state.get("hypothesis"),
        "ambiguities": state.get("ambiguities", []),
        "unsupported": state.get("unsupported", []),
        "applied_defaults": state.get("applied_defaults", []),
        "semantic_issues": state.get("semantic_issues", []),
        "spec": state.get("spec"),
        "spec_hash": state.get("spec_hash"),
        "plan": state.get("plan"),
        "plan_hash": state.get("plan_hash"),
        "data_fingerprint": state.get("data_fingerprint"),
        "approval_token": state.get("approval_token"),
        "approval_required": state.get("stage") == "await_approval"
        and not state.get("approval_granted"),
        "experiment_id": state.get("experiment_id"),
        "report": state.get("report"),
        "blocked_reason": state.get("blocked_reason"),
        "trace": state.get("stage_log", []),
        "limits": {
            "max_clarification_rounds": MAX_CLARIFICATION_ROUNDS,
            "max_repair_rounds": MAX_REPAIR_ROUNDS,
            "clarification_rounds_used": state.get("clarification_rounds", 0),
            "repair_rounds_used": state.get("repair_rounds", 0),
        },
    }
