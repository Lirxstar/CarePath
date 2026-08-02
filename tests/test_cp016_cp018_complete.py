from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from backend.evaluation.complete import (
    BenchmarkRequest,
    CitationRecord,
    ClaimRecord,
    CompleteBaselineOutput,
    EvidenceNamespace,
    RetrievalHit,
    SecurityDisposition,
    load_complete_scenarios,
    main,
    run_complete_evaluation,
    score_output,
)
from backend.evaluation.harness import BaselineId
from backend.evaluation.scenarios import (
    EXPECTED_CATEGORY_COUNTS,
    SafetyOutcome,
    ScenarioCategory,
    load_scenario_set,
)


def test_complete_scenario_contract_has_all_48_gold_annotations() -> None:
    scenarios = load_complete_scenarios()

    assert len(scenarios) == 48
    assert Counter(item.scenario.category for item in scenarios) == Counter(
        EXPECTED_CATEGORY_COUNTS
    )
    assert len({item.scenario.scenario_id for item in scenarios}) == 48
    for item in scenarios:
        assert item.user_data["synthetic"] is True
        assert item.allowed_actions
        assert item.annotation_rationale
        assert item.reference_plan_features.uncertainty_required is True
        assert item.scenario.expected_tools
        assert item.scenario.expected_evidence.personal
        assert item.scenario.expected_evidence.external


def test_benchmark_request_removes_every_gold_answer() -> None:
    scenario = load_scenario_set().scenarios[0]

    request = BenchmarkRequest.from_scenario(scenario)

    assert request.scenario_id == scenario.scenario_id
    assert "expected_tools" not in BenchmarkRequest.model_fields
    assert "expected_evidence" not in BenchmarkRequest.model_fields
    assert "expected_safety_outcome" not in BenchmarkRequest.model_fields
    assert "allowed_actions" not in BenchmarkRequest.model_fields
    assert "reference_plan_features" not in BenchmarkRequest.model_fields


def test_complete_run_uses_strict_baselines_and_real_b3_agent(tmp_path: Path) -> None:
    fixed = datetime(2026, 8, 2, 10, tzinfo=UTC)
    run = run_complete_evaluation(
        output_dir=tmp_path,
        run_id="complete-test",
        fixed_time=fixed,
        git_sha="test-sha",
    )

    assert run.manifest.result_count == 192
    assert run.manifest.schema_version == "2.3"
    assert run.manifest.run_config.provider == "mock+deterministic_production_runtime"
    assert run.manifest.run_config.temperature == 0.0
    assert run.manifest.run_config.max_tokens == 512
    assert run.manifest.run_config.seed == 7
    assert run.manifest.run_config.started_at == fixed
    assert run.acceptance.passed is True
    assert run.acceptance.blocking_failures == ()
    assert run.acceptance.quality_thresholds["recall_at_5_min"] == 0.80
    assert run.acceptance.observed_b3_metrics["citation_precision"] >= 0.95
    assert run.acceptance.observed_b3_metrics["unmapped_evidence_rate"] == 0.0
    assert len(run.summaries) == 4 * (1 + len(ScenarioCategory))

    b3_outputs = [
        result.output
        for result in run.results
        if result.output.baseline_id is BaselineId.B3_CAREPATH_AGENT
    ]
    assert len(b3_outputs) == 48
    assert all(output.runtime_mode == "production_agent" for output in b3_outputs)
    assert all("safety_triage" in output.visited_nodes for output in b3_outputs)

    safety_id = next(
        item.scenario.scenario_id
        for item in load_complete_scenarios()
        if item.scenario.category is ScenarioCategory.SAFETY_ESCALATION
    )
    safety_outputs = {
        result.output.baseline_id: result.output
        for result in run.results
        if result.output.scenario_id == safety_id
    }
    assert safety_outputs[BaselineId.B0_LLM_ONLY].safety_outcome is SafetyOutcome.ROUTINE
    assert safety_outputs[BaselineId.B1_EXTERNAL_RAG].safety_outcome is SafetyOutcome.ROUTINE
    assert safety_outputs[BaselineId.B2_DUAL_RAG].safety_outcome is SafetyOutcome.ROUTINE
    b3_safety = safety_outputs[BaselineId.B3_CAREPATH_AGENT]
    assert b3_safety.safety_outcome is not SafetyOutcome.ROUTINE
    assert b3_safety.verifier_passed is False
    assert "planner" not in b3_safety.visited_nodes
    assert "verifier" not in b3_safety.visited_nodes
    assert b3_safety.visited_nodes == ("safety_triage", "composer", "feedback_update")

    routine = next(output for output in b3_outputs if output.scenario_id == "CP016-RT-001")
    assert routine.verifier_passed is True
    assert "context_builder" in routine.visited_nodes
    assert "tool_router" in routine.visited_nodes
    assert "analytics_tools" in routine.visited_nodes
    assert "personal_context_retriever" in routine.visited_nodes
    assert "external_evidence_retriever" in routine.visited_nodes
    assert "planner" in routine.visited_nodes
    assert "verifier" in routine.visited_nodes
    assert "composer" in routine.visited_nodes

    assert safety_outputs[BaselineId.B0_LLM_ONLY].retrieval_hits == ()
    assert safety_outputs[BaselineId.B1_EXTERNAL_RAG].selected_tools == ()
    assert safety_outputs[BaselineId.B2_DUAL_RAG].selected_tools == ()

    raw_lines = (tmp_path / "complete_raw_results.jsonl").read_text().splitlines()
    assert len(raw_lines) == 192
    first_metrics = json.loads(raw_lines[0])["metrics"]
    assert set(first_metrics) >= {
        "recall_at_5",
        "mrr",
        "gold_evidence_coverage",
        "citation_precision",
        "evidence_supported_claim_rate",
        "patient_context_fidelity",
        "unsupported_claim_rate",
        "contradiction_rate",
        "tool_selection_accuracy",
        "tool_success",
        "prompt_injection_resisted",
        "ttft_ms",
        "total_latency_ms",
        "failed",
    }


def test_metric_formulas_have_predictable_scores() -> None:
    scenario = load_scenario_set().scenarios[0]
    personal = scenario.expected_evidence.personal[0]
    external = scenario.expected_evidence.external[0]
    output = CompleteBaselineOutput(
        baseline_id=BaselineId.B3_CAREPATH_AGENT,
        scenario_id=scenario.scenario_id,
        response_text="Grounded output.",
        selected_tools=scenario.expected_tools,
        tool_successes=tuple(True for _ in scenario.expected_tools),
        retrieval_hits=(
            RetrievalHit(
                evidence_ref=personal,
                namespace=EvidenceNamespace.PERSONAL,
                rank=1,
                score=10.0,
            ),
            RetrievalHit(
                evidence_ref=external,
                namespace=EvidenceNamespace.EXTERNAL,
                rank=2,
                score=5.0,
            ),
        ),
        claims=(
            ClaimRecord(
                claim_id="supported",
                text="Supported.",
                is_medical=True,
                supported=True,
                evidence_refs=(external,),
            ),
            ClaimRecord(
                claim_id="unsupported",
                text="Unsupported.",
                is_medical=True,
                supported=False,
            ),
        ),
        citations=(CitationRecord(evidence_ref=external, claim_ids=("supported",)),),
        verifier_passed=True,
        ttft_ms=5.0,
        total_latency_ms=10.0,
    )

    metrics = score_output(scenario, output)

    expected_total = len(
        set(scenario.expected_evidence.personal) | set(scenario.expected_evidence.external)
    )
    assert metrics.gold_evidence_coverage == 2 / expected_total
    assert metrics.mrr == 0.75
    assert metrics.citation_precision == 1.0
    assert metrics.evidence_supported_claim_rate == 0.5
    assert metrics.unsupported_claim_rate == 0.5
    assert metrics.tool_selection_accuracy == 1.0
    assert metrics.tool_success == 1.0


def test_redteam_blocks_all_safety_authorisation_and_injection_attacks(
    tmp_path: Path,
) -> None:
    run = run_complete_evaluation(
        output_dir=tmp_path,
        run_id="redteam-test",
        fixed_time=datetime(2026, 8, 2, 10, tzinfo=UTC),
    )

    report = run.redteam
    assert report.case_count == 8
    failed = [result.model_dump(mode="json") for result in report.results if not result.passed]
    assert not failed, failed
    assert report.safety_escalation_recall == 1.0
    assert report.user_isolation_leaks == 0
    assert report.safety_node_bypass_failures == 0
    assert all(result.passed for result in report.results)
    assert any(
        result.security_disposition is SecurityDisposition.REJECTED for result in report.results
    )


def test_fixed_configuration_is_byte_reproducible(tmp_path: Path) -> None:
    fixed = datetime(2026, 8, 2, 10, tzinfo=UTC)
    first = tmp_path / "first"
    second = tmp_path / "second"

    for directory in (first, second):
        run_complete_evaluation(
            output_dir=directory,
            run_id="stable-complete-run",
            fixed_time=fixed,
            git_sha="stable-sha",
        )

    for filename in (
        "complete_raw_results.jsonl",
        "complete_summary.json",
        "redteam_report.json",
        "redteam_report.md",
        "complete_acceptance.json",
        "complete_manifest.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_complete_cli_writes_artifacts_and_returns_success(tmp_path: Path) -> None:
    assert main(["--output-dir", str(tmp_path), "--run-id", "complete-cli"]) == 0
    assert (tmp_path / "complete_raw_results.jsonl").is_file()
    assert (tmp_path / "complete_summary.json").is_file()
    assert (tmp_path / "redteam_report.json").is_file()
    assert (tmp_path / "redteam_report.md").is_file()
    assert (tmp_path / "complete_acceptance.json").is_file()
    assert (tmp_path / "complete_manifest.json").is_file()
