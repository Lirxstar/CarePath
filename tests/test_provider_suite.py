import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from backend.api.app.llm.provider import JsonObject, LLMProvider, ProviderMetadata
from backend.evaluation import provider_suite
from backend.evaluation.provider_suite import (
    RESULT_SCHEMA,
    PhaseConfig,
    build_prompt,
    compare_phases,
    run_phase,
    run_suite,
    score_rows,
    validate_result,
)
from backend.evaluation.scenarios import EvaluationScenario, load_scenario_set


class FakeProvider(LLMProvider):
    is_local = True

    def __init__(self, *, ready: bool = True, fail: bool = False) -> None:
        scenario_set = load_scenario_set()
        self.scenarios = {scenario.scenario_id: scenario for scenario in scenario_set.scenarios}
        self.ready = ready
        self.fail = fail
        self.closed = False

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "synthetic"

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        result, _ = await self.generate_structured_with_metadata(prompt, schema, **kwargs)
        return result

    async def generate_structured_with_metadata(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> tuple[JsonObject, ProviderMetadata]:
        assert schema == RESULT_SCHEMA
        assert kwargs["seed"] == 0
        assert kwargs["max_tokens"] == 768
        assert kwargs["temperature"] == 0.0
        if self.fail:
            raise RuntimeError("synthetic provider failure")
        scenario_id = next(scenario_id for scenario_id in self.scenarios if scenario_id in prompt)
        scenario = self.scenarios[scenario_id]
        result: JsonObject = {
            "response_text": "Synthetic bounded response.",
            "selected_tools": [item.value for item in scenario.expected_tools],
            "personal_evidence_refs": list(scenario.expected_evidence.personal),
            "external_evidence_refs": list(scenario.expected_evidence.external),
            "safety_outcome": scenario.expected_safety_outcome.value,
            "security_outcome": scenario.expected_security_outcome.value,
            "response_language": scenario.expected_response_language.value,
            "prohibited_claims_present": [],
            "diagnostic_claim": False,
            "medication_change": False,
            "followed_untrusted_instruction": False,
        }
        metadata: ProviderMetadata = {
            "model": "fake-model",
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        }
        return result, metadata

    async def health_check(self) -> JsonObject:
        return {"status": "ok" if self.ready else "unavailable", "provider": "fake"}

    async def aclose(self) -> None:
        self.closed = True


def valid_result(scenario: EvaluationScenario) -> JsonObject:
    return {
        "response_text": "ok",
        "selected_tools": [item.value for item in scenario.expected_tools],
        "personal_evidence_refs": list(scenario.expected_evidence.personal),
        "external_evidence_refs": list(scenario.expected_evidence.external),
        "safety_outcome": scenario.expected_safety_outcome.value,
        "security_outcome": scenario.expected_security_outcome.value,
        "response_language": scenario.expected_response_language.value,
        "prohibited_claims_present": [],
        "diagnostic_claim": False,
        "medication_change": False,
        "followed_untrusted_instruction": False,
    }


def test_result_schema_validator_accepts_valid_and_rejects_bad_fields() -> None:
    scenario = load_scenario_set().scenarios[0]
    valid = valid_result(scenario)
    assert validate_result(valid) == (True, ())

    cases: tuple[tuple[str, object], ...] = (
        ("response_text", ""),
        ("selected_tools", ["compute_trend", "compute_trend"]),
        ("personal_evidence_refs", "not-a-list"),
        ("external_evidence_refs", [1]),
        ("safety_outcome", "invalid"),
        ("security_outcome", "invalid"),
        ("response_language", "xx"),
        ("prohibited_claims_present", ["invalid"]),
        ("diagnostic_claim", "false"),
        ("medication_change", None),
        ("followed_untrusted_instruction", 0),
    )
    for key, value in cases:
        invalid = dict(valid)
        invalid[key] = value
        ok, errors = validate_result(invalid)
        assert ok is False
        assert key in errors

    extra = dict(valid)
    extra["unexpected"] = True
    assert "keys" in validate_result(extra)[1]


def test_prompt_uses_synthetic_candidates_without_exposing_gold_labels() -> None:
    scenario = load_scenario_set().scenarios[0]
    prompt = build_prompt(scenario)

    assert scenario.scenario_id in prompt
    assert scenario.user_question in prompt
    assert "Candidate personal evidence refs" in prompt
    assert "profile:unrelated_preference" in prompt
    assert "source:unrelated_source" in prompt
    assert "Expected tools" not in prompt
    assert "Untrusted document packet" in prompt


def test_provider_suite_scores_full_fixed_workload_and_concurrency() -> None:
    scenarios = load_scenario_set().scenarios
    payload = asyncio.run(
        run_suite(
            FakeProvider(),
            scenarios,
            baseline_concurrency=1,
            optimized_concurrency=4,
            warmups=1,
        )
    )

    assert payload["scenario_suite"]["scenario_count"] == 48
    assert len(payload["scenario_suite"]["sha256"]) == 64
    assert payload["workload"]["same_prompts_and_seed_across_phases"] is True
    for phase_name in ("baseline", "optimized"):
        metrics = payload[phase_name]["metrics"]
        assert metrics["success_rate"] == 1.0
        assert metrics["schema_compliance_rate"] == 1.0
        assert metrics["tool_selection"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["patient_context"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["external_citations"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["safety_escalation_recall"] == 1.0
        assert metrics["hostile_instruction_rejection_rate"] == 1.0
        assert metrics["response_language_accuracy"] == 1.0
        assert metrics["unsupported_claim_rate"] == 0.0
        assert metrics["usage_metadata_coverage"] == 1.0
        assert metrics["completion_tokens_per_second"] is not None
        assert metrics["total_tokens_per_second"] is not None
        assert metrics["latency_p95_seconds"] is not None

    comparison = payload["comparison"]
    assert comparison["paired_scenarios"] == 48
    assert comparison["paired_behaviour_stability_rate"] == 1.0
    assert comparison["behaviour_regression_detected"] is False
    assert comparison["throughput_gain_percent"] is not None


def test_run_phase_records_controlled_provider_failure() -> None:
    scenario = load_scenario_set().scenarios[0]
    phase = asyncio.run(
        run_phase(
            FakeProvider(fail=True),
            (scenario,),
            PhaseConfig("failure", 1),
            warmups=0,
        )
    )

    row = phase["rows"][0]
    assert row["success"] is False
    assert row["error_class"] == "RuntimeError"
    assert len(row["prompt_sha256"]) == 64
    assert phase["metrics"]["success_rate"] == 0.0
    assert phase["metrics"]["schema_compliance_rate"] == 0.0


def test_score_rows_marks_unsupported_claims_and_missing_usage() -> None:
    scenario = load_scenario_set().scenarios[0]
    result = valid_result(scenario)
    result["diagnostic_claim"] = True
    result["selected_tools"] = []
    rows = [
        {
            "scenario_id": scenario.scenario_id,
            "success": True,
            "schema_valid": True,
            "elapsed_seconds": 0.25,
            "result": result,
            "metadata": {"usage": {"prompt_tokens": True, "total_tokens": -1}},
        }
    ]

    metrics = score_rows(rows, (scenario,), 0.5)

    assert metrics["unsupported_claim_rate"] == 1.0
    assert metrics["usage_metadata_coverage"] == 0.0
    assert metrics["completion_tokens_per_second"] is None
    assert metrics["tool_selection"]["precision"] is None
    assert metrics["tool_selection"]["recall"] == 0.0


def test_compare_phases_detects_behaviour_and_quality_regressions() -> None:
    scenario = load_scenario_set().scenarios[0]
    base_result = valid_result(scenario)
    changed_result = dict(base_result)
    changed_result["response_language"] = "ja" if base_result["response_language"] != "ja" else "en"
    baseline = {
        "concurrency": 1,
        "metrics": {
            "requests_per_second": 1.0,
            "schema_compliance_rate": 1.0,
            "safety_escalation_recall": 1.0,
            "hostile_instruction_rejection_rate": 1.0,
            "response_language_accuracy": 1.0,
            "unsupported_claim_rate": 0.0,
        },
        "rows": [
            {"scenario_id": scenario.scenario_id, "schema_valid": True, "result": base_result}
        ],
    }
    optimized = {
        "concurrency": 4,
        "metrics": {
            "requests_per_second": 2.0,
            "schema_compliance_rate": 0.9,
            "safety_escalation_recall": 0.9,
            "hostile_instruction_rejection_rate": 0.9,
            "response_language_accuracy": 0.9,
            "unsupported_claim_rate": 0.1,
        },
        "rows": [
            {"scenario_id": scenario.scenario_id, "schema_valid": True, "result": changed_result}
        ],
    }

    comparison = compare_phases(baseline, optimized)

    assert comparison["throughput_gain_percent"] == 100.0
    assert comparison["paired_behaviour_stability_rate"] == 0.0
    assert comparison["behaviour_regression_detected"] is True
    assert "schema_compliance_rate" in comparison["behaviour_regressions"]
    assert "unsupported_claim_rate" in comparison["behaviour_regressions"]


def test_run_suite_rejects_invalid_configuration_and_unready_provider() -> None:
    scenario = load_scenario_set().scenarios[0]

    with pytest.raises(ValueError, match="at least one scenario"):
        asyncio.run(run_suite(FakeProvider(), (), 1, 1, 0))
    with pytest.raises(ValueError, match="concurrency"):
        asyncio.run(run_suite(FakeProvider(), (scenario,), 0, 1, 0))
    with pytest.raises(ValueError, match="warmups"):
        asyncio.run(run_suite(FakeProvider(), (scenario,), 1, 1, -1))
    with pytest.raises(RuntimeError, match="not ready"):
        asyncio.run(run_suite(FakeProvider(ready=False), (scenario,), 1, 1, 0))


def test_provider_suite_cli_writes_auditable_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FakeProvider()
    output = tmp_path / "provider-suite.json"
    monkeypatch.setattr(provider_suite, "get_provider", lambda name: provider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "carepath-evaluate-provider",
            "--provider",
            "fake",
            "--limit",
            "2",
            "--warmups",
            "0",
            "--output",
            str(output),
        ],
    )

    assert provider_suite.main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scenario_suite"]["scenario_count"] == 2
    assert payload["provider_health"]["provider"] == "fake"
    assert provider.closed is True
    assert str(output) in capsys.readouterr().out


def test_provider_suite_cli_rejects_bad_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["carepath-evaluate-provider", "--provider", "fake", "--limit", "0"],
    )
    with pytest.raises(SystemExit):
        provider_suite.main()
