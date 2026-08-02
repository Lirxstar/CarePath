from __future__ import annotations

from pathlib import Path

from backend.evaluation.acceptance import AcceptanceStatus, evaluate_acceptance
from backend.evaluation.cli import main as evaluation_main
from backend.evaluation.harness import (
    BaselineId,
    EvaluationHarness,
    LatencySource,
)
from backend.evaluation.measured import ScenarioRequest, measured_mock_runners
from backend.evaluation.scenarios import load_scenario_set


def test_scenario_request_excludes_expected_answers() -> None:
    scenario = load_scenario_set().scenarios[0]

    request = ScenarioRequest.from_scenario(scenario)

    assert "expected_tools" not in request.model_fields
    assert "expected_evidence" not in request.model_fields
    assert "expected_findings" not in request.model_fields
    assert "expected_safety_outcome" not in request.model_fields
    assert request.scenario_id == scenario.scenario_id
    assert request.user_question == scenario.user_question


def test_measured_mock_run_passes_the_frozen_engineering_gate(tmp_path: Path) -> None:
    run = EvaluationHarness(measured_mock_runners()).run(
        load_scenario_set(),
        output_dir=tmp_path,
        run_id="measured-mock-test",
        execution_mode="measured_mock_provider",
        benchmark_valid=True,
    )

    report = evaluate_acceptance(run)

    assert run.manifest.result_count == 192
    assert run.summary.execution_mode == "measured_mock_provider"
    assert all(
        item.output.latency_source is LatencySource.MEASURED and item.output.latency_ms > 0
        for item in run.results
    )
    assert report.status is AcceptanceStatus.PASS
    assert report.evaluated_scenarios == 48
    assert all(result.passed for result in report.threshold_results)

    b3 = next(
        summary
        for summary in run.summary.baselines
        if summary.baseline_id is BaselineId.B3_CAREPATH_AGENT
    )
    assert b3.metrics.safety_escalation_recall == 1.0
    assert b3.metrics.tool_selection_accuracy >= 0.90
    assert b3.metrics.patient_context_fidelity >= 0.90
    assert b3.metrics.citation_precision >= 0.85
    assert b3.metrics.unsupported_claim_rate <= 0.10


def test_cli_creates_benchmark_valid_measured_mock_artifacts(tmp_path: Path) -> None:
    assert (
        evaluation_main(
            [
                "--measured-mock",
                "--benchmark-valid",
                "--run-id",
                "measured-mock-cli",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )

    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "raw_results.jsonl").is_file()
