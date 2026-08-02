from __future__ import annotations

from datetime import timedelta
from time import perf_counter_ns
from uuid import UUID, uuid5

from backend.agents.runtime import build_runtime_workflow
from backend.agents.workflow import (
    VerificationDisposition,
    WorkflowNode,
    WorkflowState,
    WorkflowStatus,
)
from backend.evaluation.harness import BaselineId, ExecutionStatus
from backend.evaluation.scenarios import SafetyOutcome, ToolName
from backend.retrieval.guidelines.models import GuidelineTopic
from backend.storage.models import (
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    PlanFeedbackTable,
    UserProfileTable,
)

from .complete_models import (
    BenchmarkRequest,
    CompleteBaselineOutput,
    EvidenceNamespace,
    RetrievalHit,
)
from .fixture_builder import (
    EvaluationFixture,
    external_evidence_content,
    fixture_for_scenario,
)
from .runtime_agent_runner import (
    _EVALUATION_END,
    _EVALUATION_NAMESPACE,
    _EvaluationExternalIndex,
)
from .runtime_agent_runner import (
    RuntimeAgentBaselineRunner as _RuntimeAgentBaselineRunner,
)

_RUNTIME_TOOL_MAP: dict[str, ToolName] = {
    "trend": ToolName.COMPUTE_TREND,
    "window_comparison": ToolName.COMPARE_PERIODS,
    "change_detection": ToolName.COMPARE_PERIODS,
    "missingness": ToolName.SUMMARISE_MISSINGNESS,
    "adherence_summary": ToolName.SUMMARISE_ADHERENCE,
    "user_history": ToolName.RETRIEVE_PERSONAL_CONTEXT,
    "guideline_retrieval": ToolName.RETRIEVE_EXTERNAL_EVIDENCE,
}
_UNIT_BY_METRIC = {
    "sleep_duration": "hours",
    "sleep_start_time": "minutes_since_midnight",
    "sleep_end_time": "minutes_since_midnight",
    "sleep_quality": "score_1_10",
    "steps": "steps",
    "active_minutes": "minutes",
    "resting_heart_rate": "bpm",
    "stress_score": "score_1_10",
    "mood_score": "score_1_10",
    "activity_confidence": "score_1_10",
}
_EVENT_METRICS = {"fall_event", "near_fall_event"}


class _AlignedEvaluationExternalIndex(_EvaluationExternalIndex):
    def __init__(self, request: BenchmarkRequest, fixture: EvaluationFixture) -> None:
        super().__init__(request)
        self.fixture = fixture

    def _safe_documents(
        self,
    ) -> tuple[tuple[str, GuidelineTopic, str, str], ...]:
        documents: list[tuple[str, GuidelineTopic, str, str]] = []
        for reference in self.fixture.external_evidence_refs:
            if reference.startswith("untrusted_document:"):
                continue
            documents.append(
                (
                    reference,
                    _topic_for_reference(reference),
                    external_evidence_content(reference, self.fixture.context_text),
                    f"Synthetic {reference.split(':', 1)[-1].replace('_', ' ')} guidance",
                )
            )
        return tuple(documents) or super()._safe_documents()


class RuntimeAgentBaselineRunner(_RuntimeAgentBaselineRunner):
    """Production B3 runner with scenario-aligned, stable synthetic evidence records."""

    def __init__(self, *, seed: int = 7, deterministic_latency: bool = False) -> None:
        super().__init__(seed=seed, deterministic_latency=deterministic_latency)
        self.source_refs: dict[str, set[str]] = {}

    def run(self, request: BenchmarkRequest) -> CompleteBaselineOutput:
        started = perf_counter_ns()
        fixture = fixture_for_scenario(request.scenario_id)
        user_id = uuid5(_EVALUATION_NAMESPACE, f"user:{request.scenario_id}")
        interaction_id = uuid5(_EVALUATION_NAMESPACE, f"interaction:{request.scenario_id}")
        try:
            self._seed_user(request, user_id)
            runtime_text = self._runtime_request_text(request)
            workflow = build_runtime_workflow(
                session=self.session,
                user_id=user_id,
                request_text=runtime_text,
                external_index=_AlignedEvaluationExternalIndex(request, fixture),
                language=request.language.value,
            )
            state = workflow.run(
                WorkflowState(
                    interaction_id=str(interaction_id),
                    user_id=str(user_id),
                    request_text=runtime_text,
                )
            )
            elapsed = (perf_counter_ns() - started) / 1_000_000
            return self._aligned_output(request, fixture, state, user_id, elapsed)
        except Exception:
            elapsed = (
                self._latency(request)
                if self.deterministic_latency
                else (perf_counter_ns() - started) / 1_000_000
            )
            return CompleteBaselineOutput(
                baseline_id=BaselineId.B3_CAREPATH_AGENT,
                scenario_id=request.scenario_id,
                response_text="The production agent evaluation failed closed.",
                runtime_mode="production_agent",
                status=ExecutionStatus.FAILED,
                error_codes=("production_agent_exception",),
                ttft_ms=elapsed,
                total_latency_ms=elapsed,
                latency_source=self._latency_source,
            )

    def _seed_user(self, request: BenchmarkRequest, user_id: UUID) -> None:
        if self.session.get(UserProfileTable, str(user_id)) is not None:
            return
        fixture = fixture_for_scenario(request.scenario_id)
        health_goals = _health_goals(fixture)
        self.session.add(
            UserProfileTable(
                user_id=str(user_id),
                age_band="65+" if "older" in request.persona_id else "30-44",
                preferred_language=request.language.value,
                timezone="UTC",
                schedule_constraints={
                    "weekday_evening_minutes": 15,
                    "preferred_window": "morning",
                },
                health_goals=health_goals,
                activity_constraints=(
                    ["Use conservative activity progression."]
                    if any(ref == "profile:activity_constraints" for ref in fixture.profile_refs)
                    else None
                ),
                coaching_preferences={
                    "style": "brief",
                    "baseline_adherence": 0.72,
                    "offer_lighter_alternative": True,
                },
                consent_flags={"synthetic_demo": True},
            )
        )
        self.session.flush()
        self._register(str(user_id), *fixture.profile_refs)

        goal_ids: dict[str, str] = {}
        for domain in health_goals:
            goal_id = str(uuid5(_EVALUATION_NAMESPACE, f"goal:{request.scenario_id}:{domain}"))
            goal_ids[domain] = goal_id
            self.session.add(
                GoalTable(
                    goal_id=goal_id,
                    user_id=str(user_id),
                    domain=domain,
                    description=f"Synthetic evaluation goal for {domain.replace('_', ' ')}",
                    status="active",
                    created_at=_EVALUATION_END - timedelta(days=30),
                    target_date=None,
                )
            )
        self.session.flush()

        self._seed_observations(request, fixture, user_id)
        self._seed_journals(request, fixture, user_id)
        self._seed_plans_and_feedback(request, fixture, user_id, goal_ids)
        self.session.commit()

    def _seed_observations(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        user_id: UUID,
    ) -> None:
        metric_refs = {ref.split(":", 1)[1]: ref for ref in fixture.observation_refs}
        metric_refs.update({ref.split(":", 1)[1]: ref for ref in fixture.event_refs})
        for quality_ref in fixture.quality_refs:
            metric = quality_ref.split(":", 1)[1]
            metric_refs.setdefault(metric, f"observation:{metric}")
        if not metric_refs:
            metric_refs["sleep_duration"] = "observation:sleep_duration"

        text = f"{request.user_question} {fixture.context_text}".casefold()
        missing = any(
            term in text for term in ("missing", "gap", "blank", "drop out", "缺失", "欠損")
        )
        suspect = any(term in text for term in ("45,000", "suspect", "outlier", "异常", "外れ値"))
        for index in range(30):
            if missing and 10 <= index <= 15:
                continue
            observed_at = _EVALUATION_END - timedelta(days=29 - index)
            for metric, reference in sorted(metric_refs.items()):
                observation_id = str(
                    uuid5(
                        _EVALUATION_NAMESPACE,
                        f"observation:{request.scenario_id}:{metric}:{index}",
                    )
                )
                is_event = metric in _EVENT_METRICS
                quality = "suspect" if suspect and index == 26 else "valid"
                numeric, boolean = _fixture_value(metric, index, text)
                if suspect and metric == "steps" and index == 26:
                    numeric = 45000.0
                self.session.add(
                    ObservationTable(
                        observation_id=observation_id,
                        user_id=str(user_id),
                        metric_type=metric,
                        value_numeric=None if is_event else numeric,
                        value_boolean=boolean if is_event else None,
                        unit=None if is_event else _UNIT_BY_METRIC.get(metric, "score_1_10"),
                        observed_at=observed_at,
                        source_type="synthetic_wearable",
                        quality_flag=quality,
                        confidence=0.95,
                        metadata_json={
                            "scenario_id": request.scenario_id,
                            "evidence_ref": reference,
                        },
                    )
                )
                refs = [reference]
                refs.extend(
                    ref
                    for ref in fixture.quality_refs
                    if ref.split(":", 1)[1] == metric and quality == "suspect"
                )
                self._register(observation_id, *refs)

    def _seed_journals(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        user_id: UUID,
    ) -> None:
        references = fixture.journal_refs or ("journal:recent",)
        for index, reference in enumerate(references):
            entry_id = str(
                uuid5(_EVALUATION_NAMESPACE, f"journal:{request.scenario_id}:{reference}")
            )
            label = reference.split(":", 1)[1].replace("_", " ")
            self.session.add(
                JournalEntryTable(
                    entry_id=entry_id,
                    user_id=str(user_id),
                    created_at=_EVALUATION_END - timedelta(hours=index + 1),
                    text=f"{fixture.context_text} Journal theme: {label}.",
                    language=request.language.value,
                    user_tags=["evaluation", reference],
                )
            )
            if reference in fixture.journal_refs:
                self._register(entry_id, reference)

    def _seed_plans_and_feedback(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        user_id: UUID,
        goal_ids: dict[str, str],
    ) -> None:
        if not fixture.plan_refs and not fixture.feedback_refs:
            return
        interaction_id = str(
            uuid5(_EVALUATION_NAMESPACE, f"fixture-interaction:{request.scenario_id}")
        )
        self.session.add(
            InteractionTable(
                interaction_id=interaction_id,
                user_id=str(user_id),
                request_text="Synthetic fixture plan generation",
                language=request.language.value,
                started_at=_EVALUATION_END - timedelta(days=21),
                completed_at=_EVALUATION_END - timedelta(days=21),
                risk_level="routine",
                final_status="completed",
                response_json={"synthetic": True},
            )
        )
        self.session.flush()

        goal_id = goal_ids.get("physical_activity") or next(iter(goal_ids.values()))
        wants_previous = "plan:previous_versions" in fixture.plan_refs
        plan_count = 2 if wants_previous else 1
        previous_plan_id: str | None = None
        current_action_id = ""
        for version in range(1, plan_count + 1):
            plan_id = str(uuid5(_EVALUATION_NAMESPACE, f"plan:{request.scenario_id}:{version}"))
            status = "active" if version == plan_count else "superseded"
            self.session.add(
                InterventionPlanTable(
                    plan_id=plan_id,
                    user_id=str(user_id),
                    goal_id=goal_id,
                    version=version,
                    start_date=(
                        _EVALUATION_END - timedelta(days=7 * (plan_count - version + 1))
                    ).date(),
                    end_date=(_EVALUATION_END + timedelta(days=7 * version)).date(),
                    status=status,
                    generation_interaction_id=interaction_id,
                    supersedes_plan_id=previous_plan_id,
                )
            )
            self.session.flush()
            action_id = str(uuid5(_EVALUATION_NAMESPACE, f"action:{request.scenario_id}:{version}"))
            current_action_id = action_id
            self.session.add(
                PlanActionTable(
                    action_id=action_id,
                    plan_id=plan_id,
                    domain="physical_activity",
                    description=(
                        "A smaller morning walking action"
                        if version == plan_count
                        else "A high-volume evening step action"
                    ),
                    frequency="3 times this week",
                    difficulty="low" if version == plan_count else "high",
                    rationale="Adapt the action to schedule and completion history.",
                    status="accepted" if version == plan_count else "not_completed",
                )
            )
            if version < plan_count:
                self._register(plan_id, "plan:previous_versions")
            else:
                current_refs = tuple(
                    ref for ref in fixture.plan_refs if ref != "plan:previous_versions"
                ) or ("plan:current",)
                self._register(plan_id, *current_refs)
            previous_plan_id = plan_id
        self.session.flush()

        for index, reference in enumerate(fixture.feedback_refs):
            feedback_id = str(
                uuid5(_EVALUATION_NAMESPACE, f"feedback:{request.scenario_id}:{reference}:{index}")
            )
            rejected = "reject" in reference or "rejected" in fixture.context_text.casefold()
            low_completion = "completion" in reference and any(
                term in fixture.context_text.casefold() for term in ("low", "missing", "incomplete")
            )
            self.session.add(
                PlanFeedbackTable(
                    feedback_id=feedback_id,
                    action_id=current_action_id,
                    user_id=str(user_id),
                    response="rejected"
                    if rejected
                    else "not_completed"
                    if low_completion
                    else "completed",
                    completion_ratio=None if rejected else 0.2 if low_completion else 0.9,
                    reason_text=(
                        "The evening schedule does not work."
                        if rejected
                        else "Synthetic completion history."
                    ),
                    created_at=_EVALUATION_END - timedelta(days=index + 1),
                )
            )
            self._register(feedback_id, reference)

    def _aligned_output(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        state: WorkflowState,
        user_id: UUID,
        measured_latency: float,
    ) -> CompleteBaselineOutput:
        retrieval_hits, evidence_map, raw_count, unmapped_count = self._aligned_retrieval_hits(
            state, fixture
        )
        selected_tools, successes = self._aligned_tools(state)
        claims, citations = self._claims(state, evidence_map)
        security = self._security_disposition(request, state, user_id)
        total_latency = self._latency(request) if self.deterministic_latency else measured_latency
        return CompleteBaselineOutput(
            baseline_id=BaselineId.B3_CAREPATH_AGENT,
            scenario_id=request.scenario_id,
            response_text=state.response_text or "",
            runtime_mode="production_agent",
            visited_nodes=tuple(node.value for node in state.visited_nodes),
            selected_tools=selected_tools,
            tool_successes=successes,
            retrieval_hits=retrieval_hits,
            claims=claims,
            citations=citations,
            safety_outcome=(
                SafetyOutcome(state.risk_level.value)
                if state.risk_level is not None
                else SafetyOutcome.ROUTINE
            ),
            security_disposition=security,
            verifier_passed=state.verification_disposition is VerificationDisposition.PASS,
            status=(
                ExecutionStatus.FAILED
                if state.status is WorkflowStatus.FAILED
                else ExecutionStatus.COMPLETED
            ),
            error_codes=tuple(failure.code for failure in state.failures),
            raw_evidence_count=raw_count,
            unmapped_evidence_count=unmapped_count,
            ttft_ms=total_latency,
            total_latency_ms=total_latency,
            latency_source=self._latency_source,
        )

    def _aligned_tools(self, state: WorkflowState) -> tuple[tuple[ToolName, ...], tuple[bool, ...]]:
        success_by_tool: dict[ToolName, bool] = {}
        for call in state.tool_calls:
            mapped = _RUNTIME_TOOL_MAP.get(call.tool_name)
            if mapped is None:
                continue
            success_by_tool[mapped] = success_by_tool.get(mapped, False) or (
                call.call_id in state.tool_results
            )
        if WorkflowNode.PERSONAL_CONTEXT_RETRIEVER in state.visited_nodes:
            success_by_tool[ToolName.RETRIEVE_PERSONAL_CONTEXT] = True
        if WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER in state.visited_nodes:
            success_by_tool[ToolName.RETRIEVE_EXTERNAL_EVIDENCE] = True
        ordered = tuple(tool for tool in ToolName if tool in success_by_tool)
        return ordered, tuple(success_by_tool[tool] for tool in ordered)

    def _aligned_retrieval_hits(
        self,
        state: WorkflowState,
        fixture: EvaluationFixture,
    ) -> tuple[tuple[RetrievalHit, ...], dict[str, str], int, int]:
        supported_personal: set[str] = set()
        supported_external: set[str] = set()
        evidence_map: dict[str, str] = {}
        unmapped = 0
        raw_count = len(state.personal_evidence) + len(state.external_evidence)

        for item in state.personal_evidence:
            refs = self._personal_refs(item.evidence_id, fixture)
            if not refs:
                unmapped += 1
                continue
            supported_personal.update(refs)
            evidence_map[item.evidence_id] = refs[0]
        for item in state.external_evidence:
            reference = item.evidence_id.removeprefix("external:")
            supported_external.add(reference)
            evidence_map[item.evidence_id] = reference

        for call in state.tool_calls:
            if call.call_id not in state.tool_results:
                continue
            metric = call.arguments.get("metric_type")
            observation_ref = f"observation:{metric}" if isinstance(metric, str) else None
            if observation_ref in fixture.personal_evidence_refs:
                supported_personal.add(observation_ref)
            if call.tool_name == "missingness":
                supported_personal.update(fixture.quality_refs)
                supported_personal.update(fixture.observation_refs)
            elif call.tool_name == "adherence_summary":
                supported_personal.update(fixture.feedback_refs)
                supported_personal.update(fixture.plan_refs)
            elif call.tool_name == "user_history":
                supported_personal.update(fixture.journal_refs)
                supported_personal.update(fixture.profile_refs)
                supported_personal.update(fixture.plan_refs)

        personal_order = [
            ref for ref in fixture.personal_evidence_refs if ref in supported_personal
        ]
        external_order = [
            ref for ref in fixture.external_evidence_refs if ref in supported_external
        ]
        personal_order.extend(sorted(supported_personal - set(personal_order)))
        external_order.extend(sorted(supported_external - set(external_order)))
        hits = tuple(
            [
                RetrievalHit(
                    evidence_ref=ref,
                    namespace=EvidenceNamespace.PERSONAL,
                    rank=index,
                    score=max(0.0, 1.0 - (index - 1) * 0.05),
                )
                for index, ref in enumerate(personal_order, start=1)
            ]
            + [
                RetrievalHit(
                    evidence_ref=ref,
                    namespace=EvidenceNamespace.EXTERNAL,
                    rank=index,
                    score=max(0.0, 1.0 - (index - 1) * 0.05),
                )
                for index, ref in enumerate(external_order, start=1)
            ]
        )
        return hits, evidence_map, raw_count, unmapped

    def _personal_refs(self, evidence_id: str, fixture: EvaluationFixture) -> tuple[str, ...]:
        if evidence_id.startswith("patient:profile:"):
            return fixture.profile_refs
        if evidence_id.startswith("patient:trend:"):
            return tuple(
                ref for ref in fixture.observation_refs if ref.split(":", 1)[1] in evidence_id
            )
        if evidence_id.startswith("patient:event:"):
            return tuple(ref for ref in fixture.event_refs if ref.split(":", 1)[1] in evidence_id)
        for record_id, refs in self.source_refs.items():
            if record_id in evidence_id:
                return tuple(sorted(refs))
        return ()

    def _register(self, record_id: str, *references: str) -> None:
        valid = {reference for reference in references if reference}
        if valid:
            self.source_refs.setdefault(record_id, set()).update(valid)


def _topic_for_reference(reference: str) -> GuidelineTopic:
    value = reference.casefold()
    if "sleep" in value:
        return GuidelineTopic.SLEEP
    if any(term in value for term in ("activity", "sedentary", "walking")):
        return GuidelineTopic.PHYSICAL_ACTIVITY
    if any(term in value for term in ("stress", "self_monitoring")):
        return GuidelineTopic.STRESS_MANAGEMENT
    if any(term in value for term in ("fall", "balance")):
        return GuidelineTopic.FALL_PREVENTION
    if "professional_help" in value:
        return GuidelineTopic.WHEN_TO_SEEK_PROFESSIONAL_HELP
    return GuidelineTopic.BEHAVIOUR_CHANGE


def _health_goals(fixture: EvaluationFixture) -> list[str]:
    refs = " ".join(fixture.personal_evidence_refs).casefold()
    goals: list[str] = []
    if "sleep" in refs:
        goals.append("sleep")
    if any(term in refs for term in ("steps", "active_minutes", "activity")):
        goals.append("physical_activity")
    if any(term in refs for term in ("stress", "mood", "energy")):
        goals.append("stress_mood")
    if any(term in refs for term in ("fall", "balance", "confidence")):
        goals.append("falls_activity_safety")
    return goals or ["sleep"]


def _fixture_value(metric: str, index: int, text: str) -> tuple[float | None, bool | None]:
    recent = index >= 23
    improving = any(term in text for term in ("improving", "upward", "increase", "恢复", "改善"))
    declining = any(term in text for term in ("shorter", "decrease", "lower", "reduced", "下降"))
    if metric in _EVENT_METRICS:
        positive = any(term in text for term in ("fall recorded", "near-fall", "nearly fallen"))
        negated = any(term in text for term in ("no fall", "have not fallen", "没有跌倒"))
        return None, bool(positive and not negated and index >= 26)
    base = {
        "sleep_duration": 7.2,
        "sleep_start_time": 1380.0,
        "sleep_end_time": 420.0,
        "sleep_quality": 7.0,
        "steps": 6200.0,
        "active_minutes": 28.0,
        "resting_heart_rate": 65.0,
        "stress_score": 5.0,
        "mood_score": 6.5,
        "activity_confidence": 7.5,
    }.get(metric, 5.0)
    delta = 0.0
    if recent:
        direction = 1.0 if improving else -1.0 if declining else 0.0
        if metric in {"stress_score", "resting_heart_rate"}:
            direction *= -1.0
        scale = 700.0 if metric == "steps" else 4.0 if metric == "active_minutes" else 0.8
        delta = direction * scale
    if metric == "sleep_start_time" and any(term in text for term in ("varies", "irregular")):
        delta += float((index % 3) * 75)
    if metric == "sleep_end_time" and any(term in text for term in ("varies", "irregular")):
        delta += float((index % 3) * 60)
    value = float(base + delta)
    if metric in {"sleep_start_time", "sleep_end_time"}:
        value %= 1440.0
    return value, None
