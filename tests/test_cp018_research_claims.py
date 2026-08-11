from __future__ import annotations

from datetime import UTC, datetime

from backend.evaluation.complete import run_complete_evaluation
from backend.evaluation.harness import BaselineId


def test_internal_research_targets_and_low_adherence_adaptation(tmp_path) -> None:
    run = run_complete_evaluation(
        output_dir=tmp_path,
        run_id="research-targets",
        fixed_time=datetime(2026, 8, 2, 12, tzinfo=UTC),
        git_sha="test-sha",
    )
    b3 = next(
        item
        for item in run.summaries
        if item.baseline_id is BaselineId.B3_CAREPATH_AGENT and item.category is None
    )
    assert b3.metrics.citation_precision >= 0.85
    assert b3.metrics.patient_context_fidelity >= 0.90
    assert b3.metrics.tool_selection_accuracy >= 0.90
    assert b3.metrics.unsupported_claim_rate <= 0.10

    report = run.plan_adaptation
    assert report["applicable_count"] == 3
    assert report["passed_count"] == 3
    assert report["passed_rate"] == 1.0
    low_adherence = [item for item in report["records"] if item["applicable"]]
    assert {item["scenario_id"] for item in low_adherence} == {
        "CP016-RT-009",
        "CP016-RT-010",
        "CP016-ML-004",
    }
    assert all(item["difficulty"] == "low" for item in low_adherence)
    assert all(item["estimated_minutes"] <= 8 for item in low_adherence)
    assert all(item["rationale"].strip() for item in low_adherence)

    review = run.low_score_review
    assert review["historical_reviewed_count"] == 31
    assert review["unreviewed_current_low_score_count"] == 0
    assert set(review["root_cause_taxonomy"]) == {"retrieval", "planning", "citation", "annotation"}

    assert run.manifest.schema_version == "2.3"
    assert (tmp_path / run.manifest.plan_adaptation_file).is_file()
    assert (tmp_path / run.manifest.low_score_review_file).is_file()
    assert (tmp_path / run.manifest.low_score_review_markdown_file).is_file()
