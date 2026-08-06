from copy import deepcopy

from backend.api.app.llm.provider import JsonObject
from evaluation.amd.local_full_run import _remove_vllm_unsupported_schema_keywords
from evaluation.amd.real_provider_suite import RESULT_SCHEMA, validate_result


def _contains_unique_items(value: object) -> bool:
    if isinstance(value, dict):
        return "uniqueItems" in value or any(
            _contains_unique_items(nested) for nested in value.values()
        )
    if isinstance(value, list):
        return any(_contains_unique_items(nested) for nested in value)
    return False


def test_vllm_schema_removes_only_unsupported_uniqueness_keywords() -> None:
    schema = deepcopy(RESULT_SCHEMA)

    assert _contains_unique_items(schema) is True

    _remove_vllm_unsupported_schema_keywords(schema)

    assert _contains_unique_items(schema) is False
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == RESULT_SCHEMA["required"]


def test_post_generation_validation_still_rejects_duplicate_array_items() -> None:
    result: JsonObject = {
        "response_text": "A bounded response.",
        "selected_tools": ["compute_trend", "compute_trend"],
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

    valid, errors = validate_result(result)

    assert valid is False
    assert "selected_tools" in errors
