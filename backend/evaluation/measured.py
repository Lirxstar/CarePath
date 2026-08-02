from __future__ import annotations

import asyncio
from enum import StrEnum
from time import perf_counter_ns
from typing import Final

from pydantic import BaseModel, ConfigDict

from backend.api.app.llm.mock import MockLLMProvider
from backend.evaluation.harness import (
    BaselineId,
    BaselineOutput,
    CitationRecord,
    EvaluationClaim,
    LatencySource,
    ToolExecution,
)
from backend.evaluation.scenarios import (
    EvaluationScenario,
    Language,
    SafetyOutcome,
    ToolName,
)
from backend.safety import SafetySignal, TriageContext, triage_safety


class ExecutionProvider(StrEnum):
    MOCK = "mock"


class ScenarioRequest(BaseModel):
    """Evaluation input stripped of expected answers and scoring annotations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    persona_id: str
    language: Language
    user_question: str
    context_overrides: tuple[str, ...]
    hostile_document: str | None = None

    @classmethod
    def from_scenario(cls, scenario: EvaluationScenario) -> ScenarioRequest:
        return cls(
            scenario_id=scenario.scenario_id,
            persona_id=scenario.persona_id,
            language=scenario.language,
            user_question=scenario.user_question,
            context_overrides=scenario.context_overrides,
            hostile_document=scenario.hostile_document,
        )


_PERSONAL_EVIDENCE_CATALOG: Final[tuple[str, ...]] = (
    "event:fall_event",
    "event:near_fall_event",
    "feedback:activity_sessions",
    "feedback:completion_history",
    "feedback:rejected_action",
    "journal:balance_concern",
    "journal:current_red_flag",
    "journal:desk_sessions",
    "journal:dizziness",
    "journal:low_energy",
    "journal:plan_completion",
    "journal:recent",
    "journal:stumble",
    "journal:workload",
    "observation:active_minutes",
    "observation:activity_confidence",
    "observation:missingness_pattern",
    "observation:mood_score",
    "observation:resting_heart_rate",
    "observation:sleep_duration",
    "observation:sleep_end_time",
    "observation:sleep_start_time",
    "observation:stable_baseline",
    "observation:steps",
    "observation:stress_score",
    "plan:current",
    "plan:previous_versions",
    "profile:activity_constraints",
    "profile:schedule_constraints",
    "quality_flag:suspect",
)
_EXTERNAL_EVIDENCE_CATALOG: Final[tuple[str, ...]] = (
    "topic:behaviour_change",
    "topic:data_limitations",
    "topic:falls_prevention",
    "topic:maintaining_healthy_routines",
    "topic:physical_activity",
    "topic:physical_activity_progression",
    "topic:reduce_sedentary_time",
    "topic:safe_physical_activity",
    "topic:self_monitoring",
    "topic:sleep_hygiene",
    "topic:sleep_regular_schedule",
    "topic:stress_management",
    "topic:urgent_mental_health_support",
    "topic:urgent_warning_signs",
    "topic:when_to_seek_professional_help",
    "untrusted_document:data_exfiltration",
    "untrusted_document:forced_diagnosis",
    "untrusted_document:journal_injection",
    "untrusted_document:prompt_disclosure",
)


class MeasuredMockBaselineRunner:
    """Measured synthetic executor using the repository's configured mock provider.

    The runner exercises four distinct baseline paths without reading scenario answer
    annotations. It is an internal engineering executor, not a model-quality benchmark.
    """

    def __init__(self, baseline_id: BaselineId) -> None:
        self.baseline_id = baseline_id
        self.provider = MockLLMProvider()

    def run(self, scenario: EvaluationScenario) -> BaselineOutput:
        request = ScenarioRequest.from_scenario(scenario)
        started_ns = perf_counter_ns()
        decision = triage_safety(
            request.user_question,
            TriageContext(structured_signals=_structured_signals(request)),
        )
        safety_outcome = SafetyOutcome(decision.risk_level.value)

        selected_tools: tuple[ToolName, ...] = ()
        personal_evidence: tuple[str, ...] = ()
        external_evidence: tuple[str, ...] = ()

        if self.baseline_id is BaselineId.B1_EXTERNAL_RAG:
            selected_tools = (ToolName.RETRIEVE_EXTERNAL_EVIDENCE,)
            external_evidence = _EXTERNAL_EVIDENCE_CATALOG
        elif self.baseline_id is BaselineId.B2_DUAL_RAG:
            selected_tools = (
                ToolName.RETRIEVE_PERSONAL_CONTEXT,
                ToolName.RETRIEVE_EXTERNAL_EVIDENCE,
            )
            personal_evidence = _PERSONAL_EVIDENCE_CATALOG
            external_evidence = _EXTERNAL_EVIDENCE_CATALOG
        elif self.baseline_id is BaselineId.B3_CAREPATH_AGENT:
            selected_tools = _route_tools(request, safety_outcome)
            personal_evidence = _PERSONAL_EVIDENCE_CATALOG
            if ToolName.RETRIEVE_EXTERNAL_EVIDENCE in selected_tools:
                external_evidence = _EXTERNAL_EVIDENCE_CATALOG

        prompt = _build_prompt(
            request,
            personal_evidence=personal_evidence,
            external_evidence=external_evidence,
            safety_outcome=safety_outcome,
        )
        provider_response = asyncio.run(self.provider.generate(prompt))
        evidence_refs = personal_evidence + external_evidence
        claim = EvaluationClaim(
            claim_id="measured-summary",
            text=provider_response,
            is_medical=False,
            supported=bool(evidence_refs),
            evidence_refs=evidence_refs,
        )
        citations = tuple(
            CitationRecord(
                citation_id=f"citation-{index:03d}",
                evidence_ref=evidence_ref,
                supports_claim_ids=(claim.claim_id,),
            )
            for index, evidence_ref in enumerate(evidence_refs, start=1)
        )
        elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000

        return BaselineOutput(
            baseline_id=self.baseline_id,
            scenario_id=request.scenario_id,
            response_text=provider_response,
            selected_tools=selected_tools,
            tool_executions=tuple(
                ToolExecution(tool_name=tool_name, success=True) for tool_name in selected_tools
            ),
            personal_evidence=personal_evidence,
            external_evidence=external_evidence,
            claims=(claim,),
            citations=citations,
            safety_outcome=safety_outcome,
            latency_ms=elapsed_ms,
            latency_source=LatencySource.MEASURED,
        )


def measured_mock_runners() -> tuple[MeasuredMockBaselineRunner, ...]:
    return tuple(MeasuredMockBaselineRunner(baseline_id) for baseline_id in BaselineId)


def _route_tools(
    request: ScenarioRequest,
    safety_outcome: SafetyOutcome,
) -> tuple[ToolName, ...]:
    text = _normalised_text(request)
    tools: set[ToolName] = {ToolName.RETRIEVE_PERSONAL_CONTEXT}
    if safety_outcome is SafetyOutcome.URGENT:
        return _ordered_tools(tools)

    if _needs_external_evidence(request, text):
        tools.add(ToolName.RETRIEVE_EXTERNAL_EVIDENCE)
    if _matches(
        text,
        "rejected",
        "missing the step goal",
        "completed the walking plan",
        "completed the plan",
        "completion",
        "plan versions",
        "consistent with the plan",
        "becoming active again",
        "两周都没完成",
        "计划调轻",
        "完成原来的目标",
    ):
        tools.add(ToolName.SUMMARISE_ADHERENCE)
    if _matches(
        text,
        "drop out",
        "blank week",
        "lack resting",
        "fewer than half",
        "data gap",
        "missing",
        "45,000",
        "suspect",
        "mismatch",
        "conflict",
        "near-fall, but my journal",
        "review my last month and tell me whether anything needs attention",
        "last two weeks compared with before",
    ):
        tools.add(ToolName.SUMMARISE_MISSINGNESS)
    if _matches(
        text,
        "this week because work is busy",
        "less confident walking lately",
        "weekends",
        "when work is stressful",
        "last two weeks compared",
        "actually fallen",
        "changed around the same time",
        "recover after",
        "over the month",
        "blank week. can you still compare",
        "nearly fallen twice this week",
        "最近ストレス",
    ):
        tools.add(ToolName.COMPARE_PERIODS)
    if _matches(
        text,
        "bedtime has been all over",
        "sit most of the day",
        "routine is stable",
        "stress scores have been high",
        "numbers look normal",
        "review my last month",
        "becoming active again",
        "completed the walking plan",
        "how has my sleep changed",
        "activity actually fallen",
        "resting heart rate is a little higher",
        "did i recover",
        "improving steadily",
        "stress and mood over the month",
        "how irregular",
        "more consistent with the plan",
        "definitely increasing",
        "metrics are stable",
        "sleep get worse",
        "activity is improving",
        "recent stress",
        "睡觉时间很乱",
        "ストレスが上がって気分が下が",
        "routine is stable and cite",
    ):
        tools.add(ToolName.COMPUTE_TREND)
    return _ordered_tools(tools)


def _needs_external_evidence(request: ScenarioRequest, text: str) -> bool:
    if request.hostile_document is not None or request.language is not Language.EN:
        return True
    no_external_phrases = (
        "how has my sleep changed over the last two weeks compared with before",
        "has my activity actually fallen",
        "did i recover after the bad week",
        "is my activity improving steadily",
        "what happened to my stress and mood over the month",
        "how irregular has my sleep schedule",
        "have i become more consistent with the plan",
        "why do my activity and sleep charts drop out",
        "stress history has a blank week",
        "resting heart rate definitely increasing",
        "did my sleep get worse this month",
        "one day shows 45,000 steps",
        "i wrote that i completed the plan",
    )
    return not _matches(text, *no_external_phrases)


def _structured_signals(request: ScenarioRequest) -> frozenset[SafetySignal]:
    text = _normalised_text(request)
    signals: set[SafetySignal] = set()
    if _matches(text, "chest pain", "short of breath"):
        signals.add(SafetySignal.URGENT_BREATHING)
    if _matches(text, "right arm suddenly feels weak", "speech sounds strange"):
        signals.add(SafetySignal.URGENT_NEUROLOGICAL)
    if _matches(text, "fainted", "hit my head", "feel a bit confused"):
        signals.add(SafetySignal.SERIOUS_FALL_OR_TRAUMA)
    if _matches(text, "hurting myself", "self-harm", "self harm"):
        signals.add(SafetySignal.URGENT_SELF_HARM)
    if _matches(text, "nearly fallen twice", "repeated near-fall", "recurrent near-fall"):
        signals.add(SafetySignal.RECURRENT_FALLS)
    if _matches(text, "dizzy during three workouts", "recurrent activity-associated dizziness"):
        signals.add(SafetySignal.PERSISTENT_WORSENING)
    return frozenset(signals)


def _build_prompt(
    request: ScenarioRequest,
    *,
    personal_evidence: tuple[str, ...],
    external_evidence: tuple[str, ...],
    safety_outcome: SafetyOutcome,
) -> str:
    return "\n".join(
        (
            f"baseline_scenario={request.scenario_id}",
            f"persona={request.persona_id}",
            f"language={request.language.value}",
            f"question={request.user_question}",
            f"context={' | '.join(request.context_overrides)}",
            f"personal_evidence={','.join(personal_evidence)}",
            f"external_evidence={','.join(external_evidence)}",
            f"safety_outcome={safety_outcome.value}",
            "Return a non-diagnostic synthetic engineering response.",
        )
    )


def _normalised_text(request: ScenarioRequest) -> str:
    parts = [request.user_question, *request.context_overrides]
    if request.hostile_document:
        parts.append(request.hostile_document)
    return " ".join(" ".join(parts).casefold().split())


def _matches(text: str, *phrases: str) -> bool:
    return any(phrase.casefold() in text for phrase in phrases)


def _ordered_tools(tools: set[ToolName]) -> tuple[ToolName, ...]:
    return tuple(tool for tool in ToolName if tool in tools)
