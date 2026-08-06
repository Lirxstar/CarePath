import asyncio
from typing import Any

from backend.api.app.llm.provider import JsonObject
from backend.evaluation.scenarios import load_scenario_set
from evaluation.amd.real_provider_suite import (
    RESULT_SCHEMA,
    build_prompt,
    run_suite,
    validate_result,
)


class FakeMeasuredProvider:
    is_local = True

    def __init__(self) -> None:
        scenario_set = load_scenario_set()
        self.scenarios = {scenario.scenario_id: scenario for scenario in scenario_set.scenarios}

    async def health_check(self) -> JsonObject:
        return {
            "status": "ok",
            "provider": "fake_radeon",
            "model": "fake-model",
            "local": True,
        }

    async def generate_structured_with_metadata(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> tuple[JsonObject, JsonObject]:
        assert schema == RESULT_SCHEMA
        assert kwargs["seed"] == 0
        await asyncio.sleep(0.005)
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
        metadata: JsonObject = {
            "model": "fake-model",
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        }
        return result, metadata


def test_result_schema_validator_rejects_missing_and_duplicate_fields() -> None:
    valid: JsonObject = {
        "response_text": "ok",
        "selected_tools": [],
        "personal_evidence_refs": [],
        "external_evidence_refs": [],
        "safety_outcome": "routine",
        "security_outcome": "not_applicable",
        "response_language": "en",
        "prohibited_claims_present": [],
        "diagnostic_claim": False,
        "medication_change": False,
        "followed_untrusted_instruction": False,
    }
    assert validate_result(valid) == (True, ())

    invalid = dict(valid)
    invalid["selected_tools"] = ["compute_trend", "compute_trend"]
    valid_result, errors = validate_result(invalid)
    assert valid_result is False
    assert "selected_tools" in errors


def test_prompt_uses_synthetic_candidates_without_exposing_gold_labels() -> None:
    scenario = load_scenario_set().scenarios[0]
    prompt = build_prompt(scenario)

    assert scenario.scenario_id in prompt
    assert scenario.user_question in prompt
    assert "Candidate personal evidence refs" in prompt
    assert "Expected tools" not in prompt
    assert "Untrusted document packet" in prompt


def test_real_provider_suite_scores_fixed_workload_and_concurrency() -> None:
    scenarios = load_scenario_set().scenarios[:8]
    payload = asyncio.run(
        run_suite(
            FakeMeasuredProvider(),
            scenarios,
            baseline_concurrency=1,
            optimized_concurrency=4,
            warmups=0,
        )
    )

    assert payload["scenario_suite"]["scenario_count"] == 8
    for phase_name in ("baseline", "optimized"):
        metrics = payload[phase_name]["metrics"]
        assert metrics["success_rate"] == 1.0
        assert metrics["schema_compliance_rate"] == 1.0
        assert metrics["tool_selection"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["patient_context"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["external_citations"] == {"precision": 1.0, "recall": 1.0}
        assert metrics["response_language_accuracy"] == 1.0
        assert metrics["unsupported_claim_rate"] == 0.0
        assert metrics["usage_metadata_coverage"] == 1.0
        assert metrics["completion_tokens_per_second"] is not None

    comparison = payload["comparison"]
    assert comparison["paired_scenarios"] == 8
    assert comparison["paired_behaviour_stability_rate"] == 1.0
    assert comparison["behaviour_regression_detected"] is False
    assert comparison["throughput_gain_percent"] is not None
    assert comparison["throughput_gain_percent"] > 0
