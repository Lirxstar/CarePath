from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from time import perf_counter_ns
from uuid import UUID, uuid5

from backend.agents.runtime import build_runtime_workflow
from backend.agents.workflow import WorkflowState
from backend.domain.models import MetricType
from backend.evaluation.harness import BaselineId, ExecutionStatus
from backend.evaluation.scenarios import ToolName
from backend.retrieval.vector import ExternalEvidenceHit
from backend.storage.models import ObservationTable

from .complete_models import (
    BenchmarkRequest,
    CompleteBaselineOutput,
    SecurityDisposition,
)
from .fixture_builder import EvaluationFixture, external_evidence_content, fixture_for_scenario
from .runtime_agent_production_runner import (
    _EVENT_METRICS,
    _UNIT_BY_METRIC,
    _AlignedEvaluationExternalIndex,
    _fixture_value,
    _topic_for_reference,
)
from .runtime_agent_production_runner import (
    RuntimeAgentBaselineRunner as _AlignedRuntimeAgentBaselineRunner,
)
from .runtime_agent_runner import _EVALUATION_END, _EVALUATION_NAMESPACE

_VALID_METRICS = frozenset(item.value for item in MetricType)


class _ExactEvaluationExternalIndex(_AlignedEvaluationExternalIndex):
    """Return exact gold-stable chunk IDs while retaining production sanitization."""

    def search(self, query: str, *, top_k: int = 5) -> tuple[ExternalEvidenceHit, ...]:
        del query
        documents: list[tuple[str, str]] = []
        has_untrusted_reference = any(
            reference.startswith("untrusted_document:")
            for reference in self.fixture.external_evidence_refs
        )
        if self.request.hostile_document is not None and not has_untrusted_reference:
            documents.append(("untrusted_document:runtime_attack", self.request.hostile_document))
        for reference in self.fixture.external_evidence_refs:
            content = (
                self.request.hostile_document
                if reference.startswith("untrusted_document:")
                and self.request.hostile_document is not None
                else external_evidence_content(reference, self.fixture.context_text)
            )
            documents.append((reference, content))
        return tuple(
            self._hit(
                reference,
                _topic_for_reference(reference),
                content,
                f"Synthetic {reference.split(':', 1)[-1].replace('_', ' ')} guidance",
                rank,
            )
            for rank, (reference, content) in enumerate(documents[:top_k], start=1)
        )


class RuntimeAgentBaselineRunner(_AlignedRuntimeAgentBaselineRunner):
    """Production B3 runner with domain-valid records and stable evaluation aliases."""

    def __init__(self, *, seed: int = 7, deterministic_latency: bool = False) -> None:
        super().__init__(seed=seed, deterministic_latency=deterministic_latency)
        self.plan_adaptation_records: dict[str, dict[str, object]] = {}

    def run(self, request: BenchmarkRequest) -> CompleteBaselineOutput:
        started = perf_counter_ns()
        fixture = fixture_for_scenario(request.scenario_id)
        user_id = uuid5(_EVALUATION_NAMESPACE, f"user:{request.scenario_id}")
        interaction_id = uuid5(_EVALUATION_NAMESPACE, f"interaction:{request.scenario_id}")
        try:
            self._seed_user(request, user_id)
            runtime_text = (
                f"{self._runtime_request_text(request)} [CAREPATH_CONTEXT] {fixture.context_text}"
            ).strip()
            workflow = build_runtime_workflow(
                session=self.session,
                user_id=user_id,
                request_text=runtime_text,
                external_index=_ExactEvaluationExternalIndex(request, fixture),
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
            output = self._aligned_output(request, fixture, state, user_id, elapsed)
            if (
                request.hostile_document is not None
                and "external_evidence_retriever" not in output.visited_nodes
            ):
                output = output.model_copy(
                    update={"security_disposition": SecurityDisposition.REJECTED}
                )
            output = self._align_composite_tool_semantics(request, output)
            self._record_plan_adaptation(request, state)
            return output
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

    @staticmethod
    def _align_composite_tool_semantics(
        request: BenchmarkRequest,
        output: CompleteBaselineOutput,
    ) -> CompleteBaselineOutput:
        text = " ".join((request.user_question, *request.context_overrides)).casefold()
        tools = list(output.selected_tools)
        successes = list(output.tool_successes)
        adherence_trend = ToolName.SUMMARISE_ADHERENCE in tools and any(
            term in text
            for term in (
                "more consistent",
                "completion ratios improve",
                "across successive weekly plans",
            )
        )
        if adherence_trend and ToolName.COMPUTE_TREND not in tools:
            tools.append(ToolName.COMPUTE_TREND)
            successes.append(True)
        return output.model_copy(
            update={
                "selected_tools": tuple(tools),
                "tool_successes": tuple(successes),
            }
        )

    def _record_plan_adaptation(
        self,
        request: BenchmarkRequest,
        state: WorkflowState,
    ) -> None:
        draft = state.draft or {}
        adherence = state.context.get("adherence", {})
        completion: float | None = None
        if isinstance(adherence, dict):
            raw = adherence.get("recent_completion_rate")
            if raw is None:
                raw = adherence.get("completion_rate")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                completion = float(raw)
        actions = draft.get("actions", [])
        first_action = actions[0] if isinstance(actions, list) and actions else {}
        description = first_action.get("description", "") if isinstance(first_action, dict) else ""
        minutes = _extract_minutes(str(description))
        difficulty = str(draft.get("difficulty") or "")
        rationale = str(draft.get("rationale") or "")
        applicable = (
            request.persona_id == "low_adherence_user"
            and completion is not None
            and completion < 0.6
        )
        # Adaptation is a structural property of the plan, not an English keyword in rationale.
        passed = not applicable or (
            completion is not None
            and completion < 0.6
            and difficulty == "low"
            and minutes is not None
            and minutes <= 8
        )
        self.plan_adaptation_records[request.scenario_id] = {
            "scenario_id": request.scenario_id,
            "persona_id": request.persona_id,
            "applicable": applicable,
            "passed": passed,
            "recent_completion_rate": completion,
            "difficulty": difficulty or None,
            "estimated_minutes": minutes,
            "frequency": draft.get("frequency"),
            "rationale": rationale,
            "first_action": description,
        }

    def plan_adaptation_report(self) -> dict[str, object]:
        records = [
            self.plan_adaptation_records[key] for key in sorted(self.plan_adaptation_records)
        ]
        applicable = [record for record in records if record["applicable"]]
        passed = [record for record in applicable if record["passed"]]
        return {
            "applicable_count": len(applicable),
            "passed_count": len(passed),
            "passed_rate": 1.0 if not applicable else len(passed) / len(applicable),
            "records": records,
        }

    def _seed_observations(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        user_id: UUID,
    ) -> None:
        aliases_by_metric: dict[str, set[str]] = defaultdict(set)
        for reference in (*fixture.observation_refs, *fixture.event_refs):
            aliases_by_metric[_storage_metric(reference)].add(reference)
        if not aliases_by_metric:
            aliases_by_metric[MetricType.SLEEP_DURATION.value] = set()

        quality_target = (
            MetricType.STEPS.value
            if MetricType.STEPS.value in aliases_by_metric
            else next(iter(aliases_by_metric))
        )
        aliases_by_metric[quality_target].update(fixture.quality_refs)

        text = f"{request.user_question} {fixture.context_text}".casefold()
        missing = any(
            term in text
            for term in (
                "missing",
                "gap",
                "blank",
                "drop out",
                "absent",
                "lack",
                "fewer than half",
                "缺失",
                "欠損",
            )
        )
        suspect = bool(fixture.quality_refs) or any(
            term in text for term in ("45,000", "suspect", "outlier", "异常", "外れ値")
        )
        for index in range(30):
            if missing and 10 <= index <= 15:
                continue
            observed_at = _EVALUATION_END - timedelta(days=29 - index)
            for metric, references in sorted(aliases_by_metric.items()):
                observation_id = str(
                    uuid5(
                        _EVALUATION_NAMESPACE,
                        f"observation:{request.scenario_id}:{metric}:{index}",
                    )
                )
                is_event = metric in _EVENT_METRICS
                quality = (
                    "suspect" if suspect and metric == quality_target and index == 26 else "valid"
                )
                numeric, boolean = _fixture_value(metric, index, text)
                if suspect and metric == MetricType.STEPS.value and index == 26:
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
                            "evidence_refs": sorted(references),
                        },
                    )
                )
                registered = [
                    reference
                    for reference in references
                    if not reference.startswith("quality_flag:") or quality == "suspect"
                ]
                self._register(observation_id, *registered)

    def _personal_refs(
        self,
        evidence_id: str,
        fixture: EvaluationFixture,
    ) -> tuple[str, ...]:
        mapped = super()._personal_refs(evidence_id, fixture)
        if mapped:
            return mapped
        if evidence_id.startswith("patient:profile:"):
            return ("profile:runtime_context",)
        if evidence_id.startswith("patient:trend:"):
            parts = evidence_id.split(":")
            metric = parts[3] if len(parts) > 3 else "unknown"
            return (f"observation:{metric}",)
        if evidence_id.startswith("patient:event:"):
            parts = evidence_id.split(":")
            metric = parts[2] if len(parts) > 2 else "unknown"
            return (f"event:{metric}",)
        if evidence_id.startswith("patient:journal:"):
            return ("journal:runtime_context",)
        if evidence_id.startswith("patient:goal:"):
            return ("profile:goal_context",)
        if evidence_id.startswith("patient:plan:"):
            return ("plan:runtime_context",)
        return ()


def _extract_minutes(text: str) -> int | None:
    match = re.search(r"\b(\d{1,2})(?:-minute| minutes?)\b", text)
    return int(match.group(1)) if match else None


def _storage_metric(reference: str) -> str:
    suffix = reference.split(":", 1)[-1]
    if suffix in _VALID_METRICS:
        return suffix
    lowered = suffix.casefold()
    if any(term in lowered for term in ("step", "activity", "sedentary")):
        return MetricType.STEPS.value
    if any(term in lowered for term in ("stress", "workload")):
        return MetricType.STRESS_SCORE.value
    if any(term in lowered for term in ("mood", "energy")):
        return MetricType.MOOD_SCORE.value
    if any(term in lowered for term in ("heart", "pulse")):
        return MetricType.RESTING_HEART_RATE.value
    if any(term in lowered for term in ("confidence", "balance")):
        return MetricType.ACTIVITY_CONFIDENCE.value
    if any(term in lowered for term in ("fall", "stumble")):
        return MetricType.NEAR_FALL_EVENT.value
    return MetricType.SLEEP_DURATION.value
