from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.evaluation.acceptance import (
    AcceptanceStatus,
    ArtifactIntegrityError,
    FailureCategory,
    evaluate_acceptance,
    load_evaluation_run,
)
from backend.evaluation.acceptance_cli import main as acceptance_main
from backend.evaluation.harness import (
    BaselineId,
    BaselineOutput,
    CitationRecord,
    EvaluationClaim,
    EvaluationHarness,
    LatencySource,
    ToolExecution,
)
from backend.evaluation.reference import reference_runners
from backend.evaluation.scenarios import (
    EvaluationScenario,
    SafetyOutcome,
    ScenarioCategory,
    load_scenario_set,
)


class _MeasuredRunner:
    def __init__(self, baseline_id: BaselineId, *, inject_failures: bool = False) -> None:
        self.baseline_id = baseline_id
        self.inject_failures = inject_failures

    def run(self, scenario: EvaluationScenario) -> BaselineOutput:
        is_b3 = self.baseline_id is BaselineId.B3_CAREPATH_AGENT
        personal = scenario.expected_evidence.personal if is_b3 else ()
        external = scenario.expected_evidence.external if is_b3 else ()
        evidence = personal + external
        selected_tools = scenario.expected_tools if is_b3 else ()
        safety_outcome = (
            scenario.expected_safety_outcome
            if scenario.category is ScenarioCategory.SAFETY_ESCALATION
            else SafetyOutcome.ROUTINE
        )
        claims = (
            EvaluationClaim(
                claim_id="supported",
                text="Synthetic engineering acceptance claim.",
                is_medical=False,
                supported=True,
                evidence_refs=evidence,
            ),
        )
        citations = tuple(
            CitationRecord(
                citation_id=f"citation-{index}",
                evidence_ref=evidence_ref,
                supports_claim_ids=("supported",),
            )
            for index, evidence_ref in enumerate(evidence, start=1)
        )

        if (
            self.inject_failures
            and is_b3
            and scenario.scenario_id == "CP016-SF-001"
        ):
            safety_outcome = SafetyOutcome.ROUTINE
            selected_tools = ()
            claims = (
                EvaluationClaim(
                    claim_id="unsupported",
                    text="Unsupported medical claim.",
                    is_medical=True,
                    supported=False,
                ),
            )
            citations = ()

        return BaselineOutput(
            baseline_id=self.baseline_id,
            scenario_id=scenario.scenario_id,
            response_text="Measured synthetic engineering output.",
            selected_tools=selected_tools,
            tool_executions=tuple(
                ToolExecution(tool_name=tool_name, success=True)
                for tool_name in selected_tools
            ),
            personal_evidence=personal,
            external_evidence=external,
            claims=claims,
            citations=citations,
            safety_outcome=safety_outcome,
            latency_ms=100.0 + list(BaselineId).index(self.baseline_id),
            latency_source=LatencySource.MEASURED,
        )


def _measured_runners(*, inject_failures: bool = False) -> tuple[_MeasuredRunner, ...]:
    return tuple(
        _MeasuredRunner(baseline_id, inject_failures=inject_failures)
        for baseline_id in BaselineId
    )


def _write_measured_run(
    output_dir: Path,
    *,
    inject_failures: bool = False,
) -> None:
    EvaluationHarness(_measured_runners(inject_failures=inject_failures)).run(
        load_scenario_set(),
        output_dir=output_dir,
        run_id="measured-acceptance-test",
        execution_mode="measured_test_fixture",
        benchmark_valid=True,
    )


def test_acceptance_gate_passes_a_complete_measured_run(tmp_path: Path) -> None:
    _write_measured_run(tmp_path)

    report = evaluate_acceptance(load_evaluation_run(tmp_path))

    assert report.status is AcceptanceStatus.PASS
    assert report.benchmark_valid is True
    assert report.evaluated_scenarios == 48
    assert all(result.passed for result in report.threshold_results)
    assert report.clinical_validation is False
    assert report.synthetic_engineering_evaluation is True


def test_reference_fixture_is_invalid_for_acceptance(tmp_path: Path) -> None:
    EvaluationHarness(reference_runners()).run(
        load_scenario_set(),
        output_dir=tmp_path,
        run_id="reference-only",
        execution_mode="deterministic_reference_fixture",
        benchmark_valid=False,
    )

    report = evaluate_acceptance(load_evaluation_run(tmp_path))

    assert report.status is AcceptanceStatus.INVALID
    assert any(
        failure.category is FailureCategory.PROVENANCE for failure in report.failures
    )
    assert {failure.code for failure in report.failures} >= {
        "benchmark_not_valid",
        "latency_not_measured",
    }


def test_failed_thresholds_are_categorised_by_scenario(tmp_path: Path) -> None:
    _write_measured_run(tmp_path, inject_failures=True)

    report = evaluate_acceptance(load_evaluation_run(tmp_path))

    assert report.status is AcceptanceStatus.FAIL
    failed_metrics = {
        result.metric for result in report.threshold_results if not result.passed
    }
    assert "safety_escalation_recall" in failed_metrics
    assert "unsupported_claim_rate" in failed_metrics
    assert any(
        failure.category is FailureCategory.SAFETY_ESCALATION
        and failure.scenario_id == "CP016-SF-001"
        for failure in report.failures
    )
    assert any(
        failure.category is FailureCategory.UNSUPPORTED_CLAIMS
        and failure.scenario_id == "CP016-SF-001"
        for failure in report.failures
    )


def test_artifact_hash_tampering_is_rejected(tmp_path: Path) -> None:
    _write_measured_run(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["run_id"] = "tampered"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="summary SHA-256 mismatch"):
        load_evaluation_run(tmp_path)


def test_acceptance_cli_writes_non_clinical_reports(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_measured_run(tmp_path)
    report_dir = tmp_path / "reports"

    assert acceptance_main([str(tmp_path), "--output-dir", str(report_dir)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    markdown = (report_dir / "acceptance_report.md").read_text(encoding="utf-8")
    assert "not clinical validation" in markdown
    assert (report_dir / "acceptance_report.json").is_file()


def test_acceptance_cli_returns_invalid_for_reference_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    EvaluationHarness(reference_runners()).run(
        load_scenario_set(),
        output_dir=tmp_path,
        run_id="reference-only",
        execution_mode="deterministic_reference_fixture",
        benchmark_valid=False,
    )

    assert acceptance_main([str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "invalid"
