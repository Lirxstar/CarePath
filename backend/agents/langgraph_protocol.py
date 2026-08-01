"""Typed LangGraph state, node protocol, routing, and privacy-minimised node audit events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel
from backend.retrieval import ExternalEvidenceHit, PatientEvidenceItem
from backend.safety import SupplementalSafetyClassifier, triage_with_supplemental

from .workflow import ToolCall, VerificationDisposition, WorkflowNode

AuditScalar = str | int | float | bool | None


class NodeResultStatus(StrEnum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILED = "failed"


class AgentRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_level: RiskLevel
    matched_rule_ids: tuple[str, ...] = ()
    policy_flags: tuple[str, ...] = ()
    allow_normal_planning: bool
    required_response_actions: tuple[str, ...] = ()
    uncertainty_reason: str | None = None


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    tool_name: str
    status: NodeResultStatus
    result_summary: dict[str, AuditScalar] = Field(default_factory=dict)
    source_record_ids: tuple[str, ...] = ()


class AgentErrorState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_name: WorkflowNode
    code: str
    retry_count: int = Field(default=0, ge=0)
    recoverable: bool = False


class NodeAuditEvent(BaseModel):
    """Audit schema with bounded summaries and references instead of raw sensitive text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    node_name: WorkflowNode
    started_at: datetime
    finished_at: datetime
    input_summary: dict[str, AuditScalar]
    record_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    tool_parameters: dict[str, AuditScalar] = Field(default_factory=dict)
    model_provider: str | None = None
    retry_count: int = Field(default=0, ge=0)
    result_status: NodeResultStatus


class AgentGraphState(BaseModel):
    """Serializable LangGraph state carrying every explicit CarePath workflow surface."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    interaction_id: str
    user_id: str
    request_text: str
    risk_assessment: AgentRiskAssessment | None = None
    patient_context: tuple[PatientEvidenceItem, ...] = ()
    selected_tools: tuple[ToolCall, ...] = ()
    tool_results: tuple[AgentToolResult, ...] = ()
    external_evidence: tuple[ExternalEvidenceHit, ...] = ()
    plan_draft: dict[str, object] | None = None
    verification_result: VerificationDisposition | None = None
    final_response: str | None = None
    error_state: AgentErrorState | None = None
    model_provider: str | None = None
    retry_count: int = Field(default=0, ge=0, le=1)
    node_audit_events: tuple[NodeAuditEvent, ...] = ()


class AgentNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_name: WorkflowNode
    state: AgentGraphState


class AgentNodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: AgentGraphState
    result_status: NodeResultStatus = NodeResultStatus.SUCCESS
    record_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    tool_parameters: dict[str, AuditScalar] = Field(default_factory=dict)


AgentNodeHandler = Callable[[AgentNodeInput], AgentNodeOutput]

_REQUIRED_NODES = (
    WorkflowNode.SAFETY_TRIAGE,
    WorkflowNode.CONTEXT_BUILDER,
    WorkflowNode.TOOL_ROUTER,
    WorkflowNode.ANALYTICS_TOOLS,
    WorkflowNode.PERSONAL_CONTEXT_RETRIEVER,
    WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER,
    WorkflowNode.PLANNER,
    WorkflowNode.VERIFIER,
    WorkflowNode.COMPOSER,
    WorkflowNode.FEEDBACK_UPDATE,
)
_SENSITIVE_PARAMETER_FRAGMENTS = (
    "api_key",
    "content",
    "journal",
    "message",
    "note",
    "prompt",
    "request",
    "secret",
    "text",
    "token",
)


def build_carepath_langgraph(handlers: Mapping[WorkflowNode, AgentNodeHandler]) -> Any:
    """Compile the bounded CarePath graph with explicit typed node boundaries."""

    missing = [node.value for node in _REQUIRED_NODES if node not in handlers]
    if missing:
        raise ValueError(f"missing LangGraph handlers: {', '.join(missing)}")

    builder = StateGraph(AgentGraphState)
    for node in _REQUIRED_NODES:
        builder.add_node(node.value, RunnableLambda(_wrap_node(node, handlers[node])))

    builder.add_edge(START, WorkflowNode.SAFETY_TRIAGE.value)
    builder.add_conditional_edges(
        WorkflowNode.SAFETY_TRIAGE.value,
        _after_safety,
        {
            WorkflowNode.CONTEXT_BUILDER.value: WorkflowNode.CONTEXT_BUILDER.value,
            WorkflowNode.COMPOSER.value: WorkflowNode.COMPOSER.value,
        },
    )
    _add_guarded_edge(builder, WorkflowNode.CONTEXT_BUILDER, WorkflowNode.TOOL_ROUTER)
    _add_guarded_edge(builder, WorkflowNode.TOOL_ROUTER, WorkflowNode.ANALYTICS_TOOLS)
    _add_guarded_edge(
        builder,
        WorkflowNode.ANALYTICS_TOOLS,
        WorkflowNode.PERSONAL_CONTEXT_RETRIEVER,
    )
    _add_guarded_edge(
        builder,
        WorkflowNode.PERSONAL_CONTEXT_RETRIEVER,
        WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER,
    )
    _add_guarded_edge(
        builder,
        WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER,
        WorkflowNode.PLANNER,
    )
    _add_guarded_edge(builder, WorkflowNode.PLANNER, WorkflowNode.VERIFIER)
    builder.add_conditional_edges(
        WorkflowNode.VERIFIER.value,
        _after_verifier,
        {
            WorkflowNode.PLANNER.value: WorkflowNode.PLANNER.value,
            WorkflowNode.COMPOSER.value: WorkflowNode.COMPOSER.value,
        },
    )
    builder.add_edge(WorkflowNode.COMPOSER.value, WorkflowNode.FEEDBACK_UPDATE.value)
    builder.add_edge(WorkflowNode.FEEDBACK_UPDATE.value, END)
    return builder.compile()


def default_safety_handler(
    classifier: SupplementalSafetyClassifier | None = None,
) -> AgentNodeHandler:
    """Return the application-controlled safety node used before any planning path."""

    def handler(node_input: AgentNodeInput) -> AgentNodeOutput:
        state = node_input.state
        decision = triage_with_supplemental(state.request_text, classifier=classifier)
        risk = AgentRiskAssessment(
            risk_level=decision.risk_level,
            matched_rule_ids=decision.matched_rule_ids,
            policy_flags=tuple(item.value for item in decision.policy_flags),
            allow_normal_planning=decision.allow_normal_planning,
            required_response_actions=tuple(
                item.value for item in decision.required_response_actions
            ),
            uncertainty_reason=decision.uncertainty_reason,
        )
        result_status = (
            NodeResultStatus.SUCCESS if decision.allow_normal_planning else NodeResultStatus.BLOCKED
        )
        return AgentNodeOutput(
            state=state.model_copy(update={"risk_assessment": risk}),
            result_status=result_status,
        )

    return handler


def passthrough_handler(node_input: AgentNodeInput) -> AgentNodeOutput:
    """Typed no-op useful for graph protocol tests and deliberately empty nodes."""

    return AgentNodeOutput(state=node_input.state)


def _wrap_node(
    node: WorkflowNode,
    handler: AgentNodeHandler,
) -> Callable[[AgentGraphState], dict[str, Any]]:
    def invoke(state_value: AgentGraphState) -> dict[str, Any]:
        state = AgentGraphState.model_validate(state_value)
        started_at = datetime.now(UTC)
        try:
            output = handler(AgentNodeInput(node_name=node, state=state))
            next_state = output.state
            if (
                next_state.interaction_id != state.interaction_id
                or next_state.user_id != state.user_id
            ):
                raise ValueError("node handlers cannot change interaction_id or user_id")
            result_status = output.result_status
            record_ids = output.record_ids
            document_ids = output.document_ids
            tool_parameters = _safe_tool_parameters(output.tool_parameters)
        except Exception:
            next_state = state.model_copy(
                update={
                    "error_state": AgentErrorState(
                        node_name=node,
                        code=f"{node.value}_failed",
                        retry_count=state.retry_count,
                    )
                }
            )
            result_status = NodeResultStatus.FAILED
            record_ids = ()
            document_ids = ()
            tool_parameters = {}

        if (
            node is WorkflowNode.VERIFIER
            and next_state.verification_result is VerificationDisposition.REGENERATE_ONCE
            and next_state.retry_count < 1
        ):
            next_state = next_state.model_copy(update={"retry_count": next_state.retry_count + 1})

        finished_at = datetime.now(UTC)
        audit_event = NodeAuditEvent(
            event_id=str(uuid4()),
            node_name=node,
            started_at=started_at,
            finished_at=finished_at,
            input_summary=_safe_input_summary(state),
            record_ids=tuple(dict.fromkeys(record_ids)),
            document_ids=tuple(dict.fromkeys(document_ids)),
            tool_parameters=tool_parameters,
            model_provider=next_state.model_provider,
            retry_count=next_state.retry_count,
            result_status=result_status,
        )
        next_state = next_state.model_copy(
            update={"node_audit_events": (*next_state.node_audit_events, audit_event)}
        )
        return next_state.model_dump(mode="python")

    return invoke


def _safe_input_summary(state: AgentGraphState) -> dict[str, AuditScalar]:
    return {
        "interaction_id": state.interaction_id,
        "user_id": state.user_id,
        "patient_evidence_count": len(state.patient_context),
        "selected_tool_count": len(state.selected_tools),
        "tool_result_count": len(state.tool_results),
        "external_evidence_count": len(state.external_evidence),
        "plan_draft_present": state.plan_draft is not None,
        "error_present": state.error_state is not None,
    }


def _safe_tool_parameters(parameters: Mapping[str, AuditScalar]) -> dict[str, AuditScalar]:
    safe: dict[str, AuditScalar] = {}
    for key, value in parameters.items():
        normalized = key.casefold()
        if any(fragment in normalized for fragment in _SENSITIVE_PARAMETER_FRAGMENTS):
            continue
        safe[key] = value
    return safe


def _after_safety(state_value: AgentGraphState) -> str:
    state = AgentGraphState.model_validate(state_value)
    if state.error_state is not None:
        return WorkflowNode.COMPOSER.value
    if state.risk_assessment is None or not state.risk_assessment.allow_normal_planning:
        return WorkflowNode.COMPOSER.value
    return WorkflowNode.CONTEXT_BUILDER.value


def _after_verifier(state_value: AgentGraphState) -> str:
    state = AgentGraphState.model_validate(state_value)
    if state.error_state is not None:
        return WorkflowNode.COMPOSER.value
    verifier_attempts = sum(
        event.node_name is WorkflowNode.VERIFIER for event in state.node_audit_events
    )
    if (
        state.verification_result is VerificationDisposition.REGENERATE_ONCE
        and state.retry_count == 1
        and verifier_attempts == 1
    ):
        return WorkflowNode.PLANNER.value
    return WorkflowNode.COMPOSER.value


def _add_guarded_edge(builder: Any, current: WorkflowNode, next_node: WorkflowNode) -> None:
    def route(state_value: AgentGraphState) -> str:
        state = AgentGraphState.model_validate(state_value)
        return WorkflowNode.COMPOSER.value if state.error_state is not None else next_node.value

    builder.add_conditional_edges(
        current.value,
        route,
        {
            next_node.value: next_node.value,
            WorkflowNode.COMPOSER.value: WorkflowNode.COMPOSER.value,
        },
    )
