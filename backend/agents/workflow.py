"""Bounded CarePath agent workflow implementing the frozen CP-009 state graph."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel
from backend.retrieval import DualRetriever, RetrievalHit
from backend.safety import triage_safety


class WorkflowNode(StrEnum):
    SAFETY_TRIAGE = "safety_triage"
    CONTEXT_BUILDER = "context_builder"
    TOOL_ROUTER = "tool_router"
    ANALYTICS_TOOLS = "analytics_tools"
    PERSONAL_CONTEXT_RETRIEVER = "personal_context_retriever"
    EXTERNAL_EVIDENCE_RETRIEVER = "external_evidence_retriever"
    PLANNER = "planner"
    VERIFIER = "verifier"
    COMPOSER = "composer"
    FEEDBACK_UPDATE = "feedback_update"


class WorkflowStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class VerificationDisposition(StrEnum):
    PASS = "pass"
    REGENERATE_ONCE = "regenerate_once"
    FALLBACK = "fallback"


class FailureKind(StrEnum):
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    NODE = "node"
    VERIFICATION = "verification"


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class WorkflowFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str
    kind: FailureKind
    code: str
    attempts: int = Field(default=1, ge=1)


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    content: str
    source_id: str | None = None


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_regenerations: int = Field(default=1, ge=0, le=1)
    max_tool_attempts: int = Field(default=2, ge=1, le=3)
    personal_retrieval_k: int = Field(default=5, ge=1, le=20)
    external_retrieval_k: int = Field(default=5, ge=1, le=20)


class WorkflowState(BaseModel):
    """Serializable state carried through every frozen workflow node."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    interaction_id: str
    user_id: str
    request_text: str
    current_node: WorkflowNode | None = None
    visited_nodes: list[WorkflowNode] = Field(default_factory=list)
    risk_level: RiskLevel | None = None
    matched_rule_ids: list[str] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    allow_normal_planning: bool | None = None
    uncertainty_reason: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    personal_evidence: list[EvidenceRef] = Field(default_factory=list)
    external_evidence: list[EvidenceRef] = Field(default_factory=list)
    draft: dict[str, Any] | None = None
    verification_disposition: VerificationDisposition | None = None
    regeneration_count: int = Field(default=0, ge=0, le=1)
    failures: list[WorkflowFailure] = Field(default_factory=list)
    response_text: str | None = None
    status: WorkflowStatus = WorkflowStatus.IN_PROGRESS


ContextBuilder = Callable[[WorkflowState], Mapping[str, Any]]
ToolRouter = Callable[[WorkflowState], Sequence[ToolCall]]
ToolExecutor = Callable[[Mapping[str, Any]], Any]
Planner = Callable[[WorkflowState], Mapping[str, Any]]
Verifier = Callable[[WorkflowState], VerificationDisposition]
Composer = Callable[[WorkflowState], str]
FeedbackUpdater = Callable[[WorkflowState], None]


class CarePathWorkflow:
    """Synchronous bounded orchestrator for the frozen CarePath workflow graph."""

    def __init__(
        self,
        *,
        context_builder: ContextBuilder,
        tool_router: ToolRouter,
        tool_executors: Mapping[str, ToolExecutor],
        retriever: DualRetriever,
        planner: Planner,
        verifier: Verifier,
        composer: Composer,
        feedback_updater: FeedbackUpdater | None = None,
        config: WorkflowConfig | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.tool_router = tool_router
        self.tool_executors = dict(tool_executors)
        self.retriever = retriever
        self.planner = planner
        self.verifier = verifier
        self.composer = composer
        self.feedback_updater = feedback_updater
        self.config = config or WorkflowConfig()

    def run(self, state: WorkflowState) -> WorkflowState:
        """Execute one bounded interaction without unbounded autonomous loops."""
        self._enter(state, WorkflowNode.SAFETY_TRIAGE)
        decision = triage_safety(state.request_text)
        state.risk_level = decision.risk_level
        state.matched_rule_ids = list(decision.matched_rule_ids)
        state.policy_flags = [flag.value for flag in decision.policy_flags]
        state.allow_normal_planning = decision.allow_normal_planning
        state.uncertainty_reason = decision.uncertainty_reason

        if not decision.allow_normal_planning:
            self._compose_controlled_safety_response(state)
            self._feedback_update(state)
            return state

        if not self._build_context(state):
            return self._finish_controlled_failure(state)
        if not self._route_tools(state):
            return self._finish_controlled_failure(state)
        if not self._run_analytics_tools(state):
            return self._finish_controlled_failure(state)
        if not self._retrieve_personal(state):
            return self._finish_controlled_failure(state)
        if not self._retrieve_external(state):
            return self._finish_controlled_failure(state)
        if not self._plan_and_verify(state):
            return self._finish_verification_fallback(state)

        self._enter(state, WorkflowNode.COMPOSER)
        try:
            state.response_text = self.composer(state)
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.COMPOSER.value,
                kind=FailureKind.NODE,
                code="composer_failed",
            )
            return self._finish_controlled_failure(state, composer_already_visited=True)
        state.status = WorkflowStatus.COMPLETED
        self._feedback_update(state)
        return state

    def _build_context(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.CONTEXT_BUILDER)
        try:
            state.context = dict(self.context_builder(state))
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.CONTEXT_BUILDER.value,
                kind=FailureKind.NODE,
                code="context_builder_failed",
            )
            return False
        return True

    def _route_tools(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.TOOL_ROUTER)
        try:
            calls = list(self.tool_router(state))
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.TOOL_ROUTER.value,
                kind=FailureKind.NODE,
                code="tool_router_failed",
            )
            return False

        for call in calls:
            if call.tool_name not in self.tool_executors:
                self._record_failure(
                    state,
                    component=call.tool_name,
                    kind=FailureKind.TOOL,
                    code="tool_not_allow_listed",
                )
                return False
        state.tool_calls = calls
        return True

    def _run_analytics_tools(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.ANALYTICS_TOOLS)
        for call in state.tool_calls:
            executor = self.tool_executors[call.tool_name]
            succeeded = False
            for attempt in range(1, self.config.max_tool_attempts + 1):
                try:
                    state.tool_results[call.call_id] = executor(call.arguments)
                    succeeded = True
                    break
                except Exception:
                    if attempt == self.config.max_tool_attempts:
                        self._record_failure(
                            state,
                            component=call.tool_name,
                            kind=FailureKind.TOOL,
                            code="tool_execution_failed",
                            attempts=attempt,
                        )
            if not succeeded:
                return False
        return True

    def _retrieve_personal(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.PERSONAL_CONTEXT_RETRIEVER)
        try:
            hits = self.retriever.personal_store.search(
                state.request_text,
                top_k=self.config.personal_retrieval_k,
                user_id=state.user_id,
            )
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.PERSONAL_CONTEXT_RETRIEVER.value,
                kind=FailureKind.RETRIEVAL,
                code="personal_retrieval_failed",
            )
            return False
        state.personal_evidence = [self._evidence_ref(hit) for hit in hits]
        return True

    def _retrieve_external(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER)
        try:
            hits = self.retriever.external_store.search(
                state.request_text,
                top_k=self.config.external_retrieval_k,
            )
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER.value,
                kind=FailureKind.RETRIEVAL,
                code="external_retrieval_failed",
            )
            return False
        state.external_evidence = [self._evidence_ref(hit) for hit in hits]
        return True

    def _plan_and_verify(self, state: WorkflowState) -> bool:
        if not self._plan(state):
            return False
        disposition = self._verify(state)
        if disposition is None:
            return False
        if disposition is VerificationDisposition.PASS:
            return True
        if disposition is VerificationDisposition.FALLBACK:
            return False

        if state.regeneration_count >= self.config.max_regenerations:
            state.verification_disposition = VerificationDisposition.FALLBACK
            self._record_failure(
                state,
                component=WorkflowNode.VERIFIER.value,
                kind=FailureKind.VERIFICATION,
                code="regeneration_limit_reached",
            )
            return False

        state.regeneration_count += 1
        if not self._plan(state):
            return False
        second_disposition = self._verify(state)
        if second_disposition is VerificationDisposition.PASS:
            return True
        if second_disposition is None:
            return False
        state.verification_disposition = VerificationDisposition.FALLBACK
        self._record_failure(
            state,
            component=WorkflowNode.VERIFIER.value,
            kind=FailureKind.VERIFICATION,
            code="verification_fallback_after_regeneration",
        )
        return False

    def _plan(self, state: WorkflowState) -> bool:
        self._enter(state, WorkflowNode.PLANNER)
        try:
            state.draft = dict(self.planner(state))
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.PLANNER.value,
                kind=FailureKind.NODE,
                code="planner_failed",
            )
            return False
        return True

    def _verify(self, state: WorkflowState) -> VerificationDisposition | None:
        self._enter(state, WorkflowNode.VERIFIER)
        try:
            disposition = self.verifier(state)
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.VERIFIER.value,
                kind=FailureKind.VERIFICATION,
                code="verifier_failed",
            )
            state.verification_disposition = VerificationDisposition.FALLBACK
            return None
        state.verification_disposition = disposition
        return disposition

    def _compose_controlled_safety_response(self, state: WorkflowState) -> None:
        self._enter(state, WorkflowNode.COMPOSER)
        if state.risk_level is RiskLevel.URGENT:
            state.response_text = (
                "CarePath cannot assess or diagnose an emergency. "
                "Please seek immediate in-person help or contact local emergency services."
            )
        else:
            state.response_text = (
                "CarePath cannot continue the normal coaching plan for this request. "
                "The safety boundary should be addressed before ordinary planning continues."
            )
        state.status = WorkflowStatus.BLOCKED

    def _finish_controlled_failure(
        self,
        state: WorkflowState,
        *,
        composer_already_visited: bool = False,
    ) -> WorkflowState:
        if not composer_already_visited:
            self._enter(state, WorkflowNode.COMPOSER)
        state.response_text = (
            "CarePath could not complete the required data or tool checks safely, "
            "so no coaching plan was generated."
        )
        state.status = WorkflowStatus.FAILED
        self._feedback_update(state)
        return state

    def _finish_verification_fallback(self, state: WorkflowState) -> WorkflowState:
        self._enter(state, WorkflowNode.COMPOSER)
        state.response_text = (
            "CarePath could not verify the generated coaching draft, "
            "so the draft was not returned as a plan."
        )
        state.status = WorkflowStatus.BLOCKED
        self._feedback_update(state)
        return state

    def _feedback_update(self, state: WorkflowState) -> None:
        self._enter(state, WorkflowNode.FEEDBACK_UPDATE)
        if self.feedback_updater is None:
            return
        try:
            self.feedback_updater(state)
        except Exception:
            self._record_failure(
                state,
                component=WorkflowNode.FEEDBACK_UPDATE.value,
                kind=FailureKind.NODE,
                code="feedback_update_failed",
            )
            if state.status is WorkflowStatus.COMPLETED:
                state.status = WorkflowStatus.FAILED

    @staticmethod
    def _enter(state: WorkflowState, node: WorkflowNode) -> None:
        state.current_node = node
        state.visited_nodes.append(node)

    @staticmethod
    def _record_failure(
        state: WorkflowState,
        *,
        component: str,
        kind: FailureKind,
        code: str,
        attempts: int = 1,
    ) -> None:
        state.failures.append(
            WorkflowFailure(
                component=component,
                kind=kind,
                code=code,
                attempts=attempts,
            )
        )

    @staticmethod
    def _evidence_ref(hit: RetrievalHit) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=hit.evidence_id,
            content=hit.content,
            source_id=hit.source_id,
        )
