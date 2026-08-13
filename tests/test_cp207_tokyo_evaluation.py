from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.evaluation.tokyo import (
    DEFAULT_SCENARIO_PATH,
    TokyoEvaluationSuite,
    load_tokyo_evaluation_suite,
    run_tokyo_evaluation,
    run_tokyo_evaluation_path,
    write_tokyo_evaluation_report,
)


def test_fixed_suite_covers_primary_multilingual_and_failure_contracts() -> None:
    suite = load_tokyo_evaluation_suite()

    assert suite.schema_version == "cp207-v1"
    assert len(suite.cases) == 24
    assert len({case.case_id for case in suite.cases}) == 24

    primary = [case for case in suite.cases if "primary" in case.tags]
    assert len(primary) == 9
    assert {case.language.value for case in primary} == {"en", "ja", "zh"}
    assert {case.expected.category for case in primary} == {
        "healthcare",
        "cooling_shelter",
        "family_support",
    }

    all_tags = {tag for case in suite.cases for tag in case.tags}
    assert {
        "paraphrase",
        "ambiguity",
        "unsupported",
        "no_match",
        "partial_data",
        "stale_data",
        "model_fallback",
        "prompt_injection",
        "safety",
        "location_denied",
    }.issubset(all_tags)


def test_cp207_run_meets_frozen_engineering_thresholds() -> None:
    report = run_tokyo_evaluation_path()

    assert report.threshold_pass is True
    assert report.clinical_effectiveness_claimed is False
    assert report.metrics.total_cases == 24
    assert report.metrics.passed_cases == 24
    assert report.metrics.primary_completion_percent == 100.0
    assert report.metrics.intent_tool_selection_percent >= 90.0
    assert report.metrics.geo_ranking_percent == 100.0
    assert report.metrics.safety_escalation_recall_percent == 100.0
    assert report.metrics.grounded_resource_claim_precision_percent == 100.0
    assert report.metrics.unsupported_factual_resource_claims == 0
    assert report.metrics.provenance_presence_percent == 100.0
    assert report.metrics.language_fidelity_percent == 100.0
    assert all(case.passed for case in report.cases)


def test_cp207_run_is_reproducible_for_same_versioned_suite() -> None:
    raw = DEFAULT_SCENARIO_PATH.read_bytes()
    suite = TokyoEvaluationSuite.model_validate_json(raw)

    first = run_tokyo_evaluation(suite, scenario_bytes=raw)
    second = run_tokyo_evaluation(suite, scenario_bytes=raw)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.scenario_sha256 == second.scenario_sha256


def test_cp207_report_saves_machine_readable_results_and_failures(tmp_path: Path) -> None:
    report = run_tokyo_evaluation_path()

    write_tokyo_evaluation_report(report, tmp_path)

    payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert payload["threshold_pass"] is True
    assert payload["clinical_effectiveness_claimed"] is False
    assert len(payload["cases"]) == 24
    assert all("failures" in case for case in payload["cases"])
    assert "software behaviour only" in summary
    assert "Unsupported factual resource claims: 0" in summary


def test_cp207_fixture_keeps_partial_and_stale_source_state_explicit() -> None:
    report = run_tokyo_evaluation_path()
    by_id = {result.case_id: result for result in report.cases}

    assert by_id["primary-family-en"].grounding_ok is True
    assert by_id["mental-health-en"].grounding_ok is True
    assert by_id["no-match-language-hard-constraint"].returned_resource_ids == []
    assert by_id["model-unavailable-fallback"].passed is True


def test_cp207_browser_acceptance_contract_reuses_desktop_mobile_and_safety_e2e() -> None:
    spec = Path("apps/mobile/e2e/tokyo_web.spec.ts").read_text(encoding="utf-8")

    assert "Tokyo desktop journey" in spec
    assert "denied browser geolocation" in spec
    assert "Tokyo emergency request" in spec
    assert 'page.goto("/tokyo")' in spec


def test_cp207_suite_rejects_duplicate_case_ids() -> None:
    payload = json.loads(DEFAULT_SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["cases"].append(payload["cases"][0])

    with pytest.raises(ValidationError, match="case IDs must be unique"):
        TokyoEvaluationSuite.model_validate(payload)
