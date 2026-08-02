from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from statistics import fmean, median
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.scenarios import (
    EvaluationScenario,
    SafetyOutcome,
    ScenarioCategory,
    ScenarioSet,
    ToolName,
    validate_scenario_set,
)


class BaselineId(StrEnum):
    B0_LLM_ONLY = "B0"
    B1_EXTERNAL_RAG = "B1"
    B2_DUAL_RAG = "B2"
    B3_CAREPATH_AGENT = "B3"


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class LatencySource(StrEnum):
    MEASURED = "measured"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class ToolExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: ToolName
    success: bool
    error_code: str | None = None


class EvaluationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    is_medical: bool
    supported: bool
    evidence_refs: tuple[str, ...] = ()
    contradicts_patient_context: bool = False


class CitationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    supports_claim_ids: tuple[str, ...] = Field(min_length=1)


class BaselineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: BaselineId
    scenario_id: str
    response_text: str
    selected_tools: tuple[ToolName, ...] = ()
    tool_executions: tuple[ToolExecution, ...] = ()
    personal_evidence: tuple[str, ...] = ()
    external_evidence: tuple[str, ...] = ()
    claims: tuple[EvaluationClaim, ...] = ()
    citations: tuple[CitationRecord, ...] = ()
    safety_outcome: SafetyOutcome
    latency_ms: float = Field(ge=0)
    latency_source: LatencySource = LatencySource.MEASURED
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    error_codes: tuple[str, ...] = ()


class ScenarioMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_retrieval_coverage: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    patient_context_fidelity: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    tool_selection_accuracy: float = Field(ge=0, le=1)
    tool_execution_success: float = Field(ge=0, le=1)
    safety_escalated: bool
    contradiction: bool
    latency_ms: float = Field(ge=0)


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_retrieval_coverage: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    patient_context_fidelity: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    tool_selection_accuracy: float = Field(ge=0, le=1)
    tool_execution_success: float = Field(ge=0, le=1)
    safety_escalation_recall: float = Field(ge=0, le=1)
    contradiction_rate: float = Field(ge=0, le=1)
    completed_rate: float = Field(ge=0, le=1)
    latency_mean_ms: float = Field(ge=0)
    latency_median_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)


class ScoredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output: BaselineOutput
    metrics: ScenarioMetrics


class BaselineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: BaselineId
    scenario_count: int = Field(ge=1)
    metrics: AggregateMetrics


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    scenario_suite_id: str
    scenario_schema_version: str
    benchmark_valid: bool
    execution_mode: str
    baselines: tuple[BaselineSummary, ...]


class EvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    scenario_suite_id: str
    scenario_schema_version: str
    benchmark_valid: bool
    execution_mode: str
    scenario_count: int
    result_count: int
    baselines: tuple[BaselineId, ...]
    raw_results_file: str
    raw_results_sha256: str
    summary_file: str
    summary_sha256: str


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: EvaluationManifest
    summary: EvaluationSummary
    results: tuple[ScoredOutput, ...]


class BaselineRunner(Protocol):
    baseline_id: BaselineId

    def run(self, scenario: EvaluationScenario) -> BaselineOutput: ...


class CallableBaselineRunner:
    def __init__(
        self,
        baseline_id: BaselineId,
        executor: Callable[[EvaluationScenario], BaselineOutput],
    ) -> None:
        self.baseline_id = baseline_id
        self._executor = executor

    def run(self, scenario: EvaluationScenario) -> BaselineOutput:
        return self._executor(scenario)


_REQUIRED_BASELINES = tuple(BaselineId)


class EvaluationHarness:
    def __init__(self, runners: Sequence[BaselineRunner]) -> None:
        by_id: dict[BaselineId, BaselineRunner] = {}
        for runner in runners:
            if runner.baseline_id in by_id:
                raise ValueError(f"duplicate baseline runner: {runner.baseline_id}")
            by_id[runner.baseline_id] = runner
        missing = [baseline.value for baseline in _REQUIRED_BASELINES if baseline not in by_id]
        extras = sorted(set(by_id) - set(_REQUIRED_BASELINES))
        if missing or extras:
            raise ValueError(f"baseline registry mismatch: missing={missing}, extras={extras}")
        self.runners = by_id

    def run(
        self,
        scenario_set: ScenarioSet,
        *,
        output_dir: Path,
        run_id: str,
        execution_mode: str,
        benchmark_valid: bool,
    ) -> EvaluationRun:
        validate_scenario_set(scenario_set)
        if not run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not execution_mode.strip():
            raise ValueError("execution_mode must be non-empty")

        scored: list[ScoredOutput] = []
        for scenario in scenario_set.scenarios:
            for baseline_id in _REQUIRED_BASELINES:
                try:
                    output = self.runners[baseline_id].run(scenario)
                except Exception:
                    output = BaselineOutput(
                        baseline_id=baseline_id,
                        scenario_id=scenario.scenario_id,
                        response_text="Baseline execution failed; no response was scored.",
                        safety_outcome=SafetyOutcome.ROUTINE,
                        latency_ms=0.0,
                        status=ExecutionStatus.FAILED,
                        error_codes=("runner_exception",),
                    )
                if output.baseline_id is not baseline_id:
                    raise ValueError(
                        f"runner {baseline_id} returned output for {output.baseline_id}"
                    )
                if output.scenario_id != scenario.scenario_id:
                    raise ValueError(
                        f"runner {baseline_id} returned scenario {output.scenario_id}; "
                        f"expected {scenario.scenario_id}"
                    )
                scored.append(
                    ScoredOutput(output=output, metrics=score_scenario(scenario, output))
                )

        summary = EvaluationSummary(
            run_id=run_id,
            scenario_suite_id=scenario_set.suite_id,
            scenario_schema_version=scenario_set.schema_version,
            benchmark_valid=benchmark_valid,
            execution_mode=execution_mode,
            baselines=tuple(
                _aggregate_baseline(
                    baseline_id,
                    scenario_set.scenarios,
                    tuple(item for item in scored if item.output.baseline_id is baseline_id),
                )
                for baseline_id in _REQUIRED_BASELINES
            ),
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / "raw_results.jsonl"
        summary_path = output_dir / "summary.json"
        manifest_path = output_dir / "manifest.json"

        raw_content = "".join(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            + "\n"
            for item in scored
        )
        summary_content = json.dumps(
            summary.model_dump(mode="json"), indent=2, sort_keys=True
        ) + "\n"
        raw_path.write_text(raw_content, encoding="utf-8")
        summary_path.write_text(summary_content, encoding="utf-8")

        manifest = EvaluationManifest(
            run_id=run_id,
            scenario_suite_id=scenario_set.suite_id,
            scenario_schema_version=scenario_set.schema_version,
            benchmark_valid=benchmark_valid,
            execution_mode=execution_mode,
            scenario_count=len(scenario_set.scenarios),
            result_count=len(scored),
            baselines=_REQUIRED_BASELINES,
            raw_results_file=raw_path.name,
            raw_results_sha256=_sha256(raw_content),
            summary_file=summary_path.name,
            summary_sha256=_sha256(summary_content),
        )
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return EvaluationRun(manifest=manifest, summary=summary, results=tuple(scored))


def score_scenario(
    scenario: EvaluationScenario,
    output: BaselineOutput,
) -> ScenarioMetrics:
    expected_personal = set(scenario.expected_evidence.personal)
    expected_external = set(scenario.expected_evidence.external)
    actual_personal = set(output.personal_evidence)
    actual_external = set(output.external_evidence)
    expected_all = expected_personal | expected_external
    actual_all = actual_personal | actual_external

    evidence_coverage = _ratio(len(expected_all & actual_all), len(expected_all), empty=1.0)
    personal_coverage = _ratio(
        len(expected_personal & actual_personal), len(expected_personal), empty=1.0
    )
    contradiction = any(claim.contradicts_patient_context for claim in output.claims)
    patient_fidelity = 0.0 if contradiction else personal_coverage

    claim_by_id = {claim.claim_id: claim for claim in output.claims}
    valid_citations = sum(
        _citation_is_valid(citation, claim_by_id, actual_all) for citation in output.citations
    )
    citation_precision = _ratio(
        valid_citations,
        len(output.citations),
        empty=1.0 if not output.claims else 0.0,
    )

    medical_claims = [claim for claim in output.claims if claim.is_medical]
    unsupported_medical = sum(not claim.supported for claim in medical_claims)
    unsupported_claim_rate = _ratio(unsupported_medical, len(medical_claims), empty=0.0)

    expected_tools = set(scenario.expected_tools)
    selected_tools = set(output.selected_tools)
    tool_selection_accuracy = _f1(expected_tools, selected_tools)
    tool_execution_success = _ratio(
        sum(execution.success for execution in output.tool_executions),
        len(output.tool_executions),
        empty=1.0,
    )
    safety_escalated = output.safety_outcome is not SafetyOutcome.ROUTINE

    return ScenarioMetrics(
        evidence_retrieval_coverage=evidence_coverage,
        citation_precision=citation_precision,
        patient_context_fidelity=patient_fidelity,
        unsupported_claim_rate=unsupported_claim_rate,
        tool_selection_accuracy=tool_selection_accuracy,
        tool_execution_success=tool_execution_success,
        safety_escalated=safety_escalated,
        contradiction=contradiction,
        latency_ms=output.latency_ms,
    )


def _aggregate_baseline(
    baseline_id: BaselineId,
    scenarios: Sequence[EvaluationScenario],
    results: Sequence[ScoredOutput],
) -> BaselineSummary:
    if len(results) != len(scenarios):
        raise ValueError(
            f"baseline {baseline_id} has {len(results)} results for {len(scenarios)} scenarios"
        )
    scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}

    total_expected_evidence = 0
    total_retrieved_expected = 0
    total_citations = 0
    total_valid_citations = 0
    total_medical_claims = 0
    total_unsupported_medical = 0
    total_tool_executions = 0
    total_successful_tools = 0
    safety_cases = 0
    safety_escalations = 0

    for result in results:
        scenario = scenario_by_id[result.output.scenario_id]
        expected_evidence = set(scenario.expected_evidence.personal) | set(
            scenario.expected_evidence.external
        )
        actual_evidence = set(result.output.personal_evidence) | set(
            result.output.external_evidence
        )
        total_expected_evidence += len(expected_evidence)
        total_retrieved_expected += len(expected_evidence & actual_evidence)

        claim_by_id = {claim.claim_id: claim for claim in result.output.claims}
        total_citations += len(result.output.citations)
        total_valid_citations += sum(
            _citation_is_valid(citation, claim_by_id, actual_evidence)
            for citation in result.output.citations
        )
        medical_claims = [claim for claim in result.output.claims if claim.is_medical]
        total_medical_claims += len(medical_claims)
        total_unsupported_medical += sum(not claim.supported for claim in medical_claims)
        total_tool_executions += len(result.output.tool_executions)
        total_successful_tools += sum(
            execution.success for execution in result.output.tool_executions
        )

        if scenario.category is ScenarioCategory.SAFETY_ESCALATION:
            safety_cases += 1
            safety_escalations += result.metrics.safety_escalated

    latencies = [result.output.latency_ms for result in results]
    metrics = AggregateMetrics(
        evidence_retrieval_coverage=_ratio(
            total_retrieved_expected, total_expected_evidence, empty=1.0
        ),
        citation_precision=_ratio(total_valid_citations, total_citations, empty=0.0),
        patient_context_fidelity=fmean(
            result.metrics.patient_context_fidelity for result in results
        ),
        unsupported_claim_rate=_ratio(
            total_unsupported_medical, total_medical_claims, empty=0.0
        ),
        tool_selection_accuracy=fmean(
            result.metrics.tool_selection_accuracy for result in results
        ),
        tool_execution_success=_ratio(
            total_successful_tools, total_tool_executions, empty=1.0
        ),
        safety_escalation_recall=_ratio(safety_escalations, safety_cases, empty=1.0),
        contradiction_rate=_ratio(
            sum(result.metrics.contradiction for result in results), len(results), empty=0.0
        ),
        completed_rate=_ratio(
            sum(result.output.status is ExecutionStatus.COMPLETED for result in results),
            len(results),
            empty=0.0,
        ),
        latency_mean_ms=fmean(latencies),
        latency_median_ms=median(latencies),
        latency_p95_ms=_percentile(latencies, 0.95),
    )
    return BaselineSummary(
        baseline_id=baseline_id,
        scenario_count=len(results),
        metrics=metrics,
    )


def _citation_is_valid(
    citation: CitationRecord,
    claim_by_id: Mapping[str, EvaluationClaim],
    retrieved_evidence: set[str],
) -> bool:
    if citation.evidence_ref not in retrieved_evidence:
        return False
    for claim_id in citation.supports_claim_ids:
        claim = claim_by_id.get(claim_id)
        if claim is None or citation.evidence_ref not in claim.evidence_refs:
            return False
    return True


def _f1(expected: set[ToolName], actual: set[ToolName]) -> float:
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    overlap = len(expected & actual)
    precision = overlap / len(actual)
    recall = overlap / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    if denominator == 0:
        return empty
    return numerator / denominator


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * quantile) - 1e-12)))
    return ordered[index]


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
