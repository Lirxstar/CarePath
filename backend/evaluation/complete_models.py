from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.harness import BaselineId, ExecutionStatus, LatencySource
from backend.evaluation.scenarios import (
    EvaluationScenario,
    Language,
    SafetyOutcome,
    ScenarioCategory,
    ToolName,
)


class SecurityDisposition(StrEnum):
    NOT_EXPOSED = "not_exposed"
    VULNERABLE = "vulnerable"
    REJECTED = "rejected"


class EvidenceNamespace(StrEnum):
    PERSONAL = "personal"
    EXTERNAL = "external"


class AllowedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    difficulty: str = Field(pattern=r"^(none|low|moderate)$")
    safety_constraints: tuple[str, ...] = Field(min_length=1)


class ReferencePlanFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_days: int = Field(ge=0, le=14)
    max_actions: int = Field(ge=0, le=3)
    target_difficulty: str = Field(pattern=r"^(none|low|moderate)$")
    adapt_to_adherence: bool
    uncertainty_required: bool


class CompleteScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: EvaluationScenario
    user_data: dict[str, object]
    allowed_actions: tuple[AllowedAction, ...]
    reference_plan_features: ReferencePlanFeatures
    annotation_rationale: str = Field(min_length=1)


class BenchmarkRequest(BaseModel):
    """Execution input with every gold answer and scoring field removed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    persona_id: str
    language: Language
    user_question: str
    context_overrides: tuple[str, ...]
    hostile_document: str | None = None

    @classmethod
    def from_scenario(cls, scenario: EvaluationScenario) -> "BenchmarkRequest":
        return cls(
            scenario_id=scenario.scenario_id,
            persona_id=scenario.persona_id,
            language=scenario.language,
            user_question=scenario.user_question,
            context_overrides=scenario.context_overrides,
            hostile_document=scenario.hostile_document,
        )


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str
    namespace: EvidenceNamespace
    rank: int = Field(ge=1)
    score: float = Field(ge=0)


class ClaimRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    text: str
    is_medical: bool
    supported: bool
    evidence_refs: tuple[str, ...] = ()
    contradicts_patient_context: bool = False


class CitationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str
    claim_ids: tuple[str, ...] = Field(min_length=1)


class CompleteBaselineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: BaselineId
    scenario_id: str
    response_text: str
    selected_tools: tuple[ToolName, ...] = ()
    tool_successes: tuple[bool, ...] = ()
    retrieval_hits: tuple[RetrievalHit, ...] = ()
    claims: tuple[ClaimRecord, ...] = ()
    citations: tuple[CitationRecord, ...] = ()
    safety_outcome: SafetyOutcome = SafetyOutcome.ROUTINE
    security_disposition: SecurityDisposition = SecurityDisposition.NOT_EXPOSED
    verifier_passed: bool = False
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    error_codes: tuple[str, ...] = ()
    ttft_ms: float = Field(ge=0)
    total_latency_ms: float = Field(ge=0)
    latency_source: LatencySource = LatencySource.MEASURED


class ScenarioMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recall_at_5: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    gold_evidence_coverage: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    evidence_supported_claim_rate: float = Field(ge=0, le=1)
    patient_context_fidelity: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    contradiction_rate: float = Field(ge=0, le=1)
    tool_selection_accuracy: float = Field(ge=0, le=1)
    tool_success: float = Field(ge=0, le=1)
    safety_escalated: bool
    prompt_injection_resisted: bool | None
    ttft_ms: float = Field(ge=0)
    total_latency_ms: float = Field(ge=0)
    failed: bool


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recall_at_5: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    gold_evidence_coverage: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    evidence_supported_claim_rate: float = Field(ge=0, le=1)
    patient_context_fidelity: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    contradiction_rate: float = Field(ge=0, le=1)
    tool_selection_accuracy: float = Field(ge=0, le=1)
    tool_success: float = Field(ge=0, le=1)
    safety_escalation_recall: float = Field(ge=0, le=1)
    prompt_injection_resistance: float = Field(ge=0, le=1)
    ttft_mean_ms: float = Field(ge=0)
    ttft_median_ms: float = Field(ge=0)
    ttft_p95_ms: float = Field(ge=0)
    latency_mean_ms: float = Field(ge=0)
    latency_median_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)
    failure_rate: float = Field(ge=0, le=1)


class ScoredResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ScenarioCategory
    output: CompleteBaselineOutput
    metrics: ScenarioMetrics


class GroupSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: BaselineId
    category: ScenarioCategory | None
    scenario_count: int = Field(ge=1)
    metrics: AggregateMetrics


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    temperature: float
    max_tokens: int = Field(ge=1)
    seed: int
    git_sha: str
    started_at: datetime
    completed_at: datetime
    latency_source: LatencySource


class CompleteManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    suite_id: str
    schema_version: str
    result_count: int
    run_config: RunConfig
    raw_results_file: str
    raw_results_sha256: str
    summary_file: str
    summary_sha256: str
    redteam_file: str
    redteam_sha256: str
    redteam_markdown_file: str
    redteam_markdown_sha256: str
    acceptance_file: str
    acceptance_sha256: str


class RedTeamCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    attack_type: str
    request: BenchmarkRequest
    expected_safety: SafetyOutcome
    expect_security_rejection: bool
    forbidden_phrases: tuple[str, ...]


class RedTeamResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    attack_type: str
    passed: bool
    safety_outcome: SafetyOutcome
    security_disposition: SecurityDisposition
    failed_checks: tuple[str, ...]


class RedTeamReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: int
    passed_count: int
    safety_escalation_recall: float = Field(ge=0, le=1)
    user_isolation_leaks: int = Field(ge=0)
    safety_node_bypass_failures: int = Field(ge=0)
    results: tuple[RedTeamResult, ...]


class CompleteAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    blocking_failures: tuple[str, ...]
    evaluated_scenarios: int
    evaluated_results: int


class CompleteRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: CompleteManifest
    results: tuple[ScoredResult, ...]
    summaries: tuple[GroupSummary, ...]
    redteam: RedTeamReport
    acceptance: CompleteAcceptanceReport
