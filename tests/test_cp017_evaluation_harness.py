from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.evaluation.cli import main as evaluation_main
from backend.evaluation.harness import (
    BaselineId,
    BaselineOutput,
    BaselineSummary,
    CallableBaselineRunner,
    CitationRecord,
    EvaluationClaim,
    EvaluationHarness,
    EvaluationRun,
    ExecutionStatus,
    LatencySource,
    ToolExecution,
    score_scenario,
)
from backend.evaluation.recorded import load_recorded_runners
from backend.evaluation.reference import reference_runners
from backend.evaluation.scenarios import SafetyOutcome, load_scenario_set


def _summary_by_id(run: EvaluationRun) -> dict[BaselineId, BaselineSummary]:
    return {summary.baseline_id: summary for summary in run.summary.baselines}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reference_fixture_runs_all_four_baselines_and_writes_outputs(
    tmp_path: Path,
) -> None:
    scenario_set = load_scenario_set()
    output_dir = tmp_path / "run"

    run = EvaluationHarness(reference_runners()).run(
        scenario_set,
        output_dir=output_dir,
        run_id="reference-test",
        execution_mode="deterministic_reference_fixture",
        benchmark_valid=False,
    )

    assert run.manifest.scenario_count == 48
    assert run.manifest.result_count == 192
    assert run.manifest.baselines == tuple(BaselineId)
    assert run.summary.benchmark_valid is False
    assert len(run.results) == 192
    assert all(
        item.output.latency_source is LatencySource.SYNTHETIC_FIXTURE for item in run.results
    )
    assert len((output_dir / "raw_results.jsonl").read_text().splitlines()) == 192
    assert run.manifest.raw_results_sha256 == _sha256(output_dir / "raw_results.jsonl")
    assert run.manifest.summary_sha256 == _sha256(output_dir / "summary.json")

    by_id = _summary_by_id(run)
    assert by_id[BaselineId.B0_LLM_ONLY].metrics.evidence_retrieval_coverage == 0.0
    assert 0.0 < by_id[BaselineId.B1_EXTERNAL_RAG].metrics.evidence_retrieval_coverage < 1.0
    assert by_id[BaselineId.B2_DUAL_RAG].metrics.evidence_retrieval_coverage == 1.0
    assert by_id[BaselineId.B3_CAREPATH_AGENT].metrics.evidence_retrieval_coverage == 1.0
    assert by_id[BaselineId.B3_CAREPATH_AGENT].metrics.tool_selection_accuracy == 1.0


def test_reference_fixture_is_byte_reproducible(tmp_path: Path) -> None:
    scenario_set = load_scenario_set()
    first = tmp_path / "first"
    second = tmp_path / "second"

    for output_dir in (first, second):
        EvaluationHarness(reference_runners()).run(
            scenario_set,
            output_dir=output_dir,
            run_id="stable-run",
            execution_mode="deterministic_reference_fixture",
            benchmark_valid=False,
        )

    for filename in ("raw_results.jsonl", "summary.json", "manifest.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_score_scenario_calculates_required_metrics() -> None:
    scenario = load_scenario_set().scenarios[0]
    personal_ref = scenario.expected_evidence.personal[0]
    external_ref = scenario.expected_evidence.external[0]
    selected_tool = scenario.expected_tools[0]
    output = BaselineOutput(
        baseline_id=BaselineId.B3_CAREPATH_AGENT,
        scenario_id=scenario.scenario_id,
        response_text="A scored response.",
        selected_tools=(selected_tool,),
        tool_executions=(ToolExecution(tool_name=selected_tool, success=True),),
        personal_evidence=(personal_ref,),
        external_evidence=(external_ref,),
        claims=(
            EvaluationClaim(
                claim_id="supported",
                text="Supported claim.",
                is_medical=True,
                supported=True,
                evidence_refs=(personal_ref, external_ref),
            ),
            EvaluationClaim(
                claim_id="unsupported",
                text="Unsupported claim.",
                is_medical=True,
                supported=False,
                contradicts_patient_context=True,
            ),
        ),
        citations=(
            CitationRecord(
                citation_id="valid",
                evidence_ref=external_ref,
                supports_claim_ids=("supported",),
            ),
            CitationRecord(
                citation_id="invalid",
                evidence_ref="external:not-retrieved",
                supports_claim_ids=("supported",),
            ),
        ),
        safety_outcome=SafetyOutcome.ROUTINE,
        latency_ms=123.0,
    )

    metrics = score_scenario(scenario, output)

    expected_total = len(
        set(scenario.expected_evidence.personal) | set(scenario.expected_evidence.external)
    )
    assert metrics.evidence_retrieval_coverage == pytest.approx(2 / expected_total)
    assert metrics.citation_precision == 0.5
    assert metrics.patient_context_fidelity == 0.0
    assert metrics.unsupported_claim_rate == 0.5
    assert metrics.tool_selection_accuracy == pytest.approx(
        2 / (len(set(scenario.expected_tools)) + 1)
    )
    assert metrics.tool_execution_success == 1.0
    assert metrics.contradiction is True
    assert metrics.latency_ms == 123.0


def test_harness_requires_one_runner_for_each_baseline() -> None:
    with pytest.raises(ValueError, match="baseline registry mismatch"):
        EvaluationHarness(reference_runners()[:-1])

    duplicated = (*reference_runners(), reference_runners()[0])
    with pytest.raises(ValueError, match="duplicate baseline runner"):
        EvaluationHarness(duplicated)


def test_runner_failures_are_recorded_without_aborting_the_run(tmp_path: Path) -> None:
    def fail(_: object) -> BaselineOutput:
        raise RuntimeError("deliberate test failure")

    reference = reference_runners()
    runners = (
        CallableBaselineRunner(BaselineId.B0_LLM_ONLY, fail),
        reference[1],
        reference[2],
        reference[3],
    )
    run = EvaluationHarness(runners).run(
        load_scenario_set(),
        output_dir=tmp_path,
        run_id="failure-recording",
        execution_mode="test",
        benchmark_valid=False,
    )

    failed = [item for item in run.results if item.output.baseline_id is BaselineId.B0_LLM_ONLY]
    assert len(failed) == 48
    assert all(item.output.status is ExecutionStatus.FAILED for item in failed)
    assert all(item.output.error_codes == ("runner_exception",) for item in failed)
    assert _summary_by_id(run)[BaselineId.B0_LLM_ONLY].metrics.completed_rate == 0.0


def test_recorded_outputs_use_the_same_interface_and_validate_latency(
    tmp_path: Path,
) -> None:
    scenario_set = load_scenario_set()
    reference_run = EvaluationHarness(reference_runners()).run(
        scenario_set,
        output_dir=tmp_path / "reference",
        run_id="reference",
        execution_mode="deterministic_reference_fixture",
        benchmark_valid=False,
    )
    recorded_path = tmp_path / "recorded.jsonl"
    recorded_path.write_text(
        "".join(
            json.dumps(
                item.output.model_copy(
                    update={"latency_source": LatencySource.MEASURED}
                ).model_dump(mode="json"),
                sort_keys=True,
            )
            + "\n"
            for item in reference_run.results
        ),
        encoding="utf-8",
    )

    recorded_run = EvaluationHarness(
        load_recorded_runners(recorded_path, require_measured_latency=True)
    ).run(
        scenario_set,
        output_dir=tmp_path / "recorded-run",
        run_id="measured-recorded",
        execution_mode="recorded_baseline_outputs",
        benchmark_valid=True,
    )

    assert recorded_run.summary.benchmark_valid is True
    assert recorded_run.manifest.result_count == 192

    synthetic_path = tmp_path / "synthetic.jsonl"
    synthetic_path.write_text(
        json.dumps(reference_run.results[0].output.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires measured latency"):
        load_recorded_runners(synthetic_path, require_measured_latency=True)


def test_evaluation_cli_writes_reference_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "cli"

    assert (
        evaluation_main(
            [
                "--output-dir",
                str(output_dir),
                "--run-id",
                "cli-reference",
            ]
        )
        == 0
    )

    printed = json.loads(capsys.readouterr().out)
    assert printed["run_id"] == "cli-reference"
    assert printed["benchmark_valid"] is False
    assert (output_dir / "manifest.json").is_file()
