import json
from pathlib import Path

from backend.api.app.llm.radeon_cloud import RadeonCloudProvider
from backend.api.app.llm.radeon_local import RadeonLocalProvider

EVIDENCE_PATH = Path("evaluation/amd/results/dedicated_radeon_environment.json")


def test_safe_usage_metadata_keeps_only_non_secret_fields() -> None:
    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "choices": [{"finish_reason": "stop", "message": {"content": "secret response"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "prompt_text": "must not be copied",
        },
        "api_key": "must not be copied",
        "endpoint": "must not be copied",
    }
    expected = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    assert RadeonCloudProvider._safe_response_metadata(payload) == expected
    assert RadeonLocalProvider._safe_response_metadata(payload) == expected


def test_dedicated_environment_evidence_is_sanitized_and_explicitly_limited() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert payload["deployment"] == "dedicated_radeon_cloud"
    assert payload["local_to_end_user"] is False
    assert payload["hardware"]["gfx_architecture"] == "gfx1100"
    assert payload["hardware"]["compute_units"] == 96
    assert payload["driver_and_runtime"]["rocm_version"] == "7.2.1"
    assert payload["model_and_serve_config"]["model_id"] == "Qwen/Qwen2.5-7B-Instruct"
    assert payload["carepath"]["commit_verified_by_git_rev_parse"] is False
    assert payload["limitations"]

    serialized = json.dumps(payload).casefold()
    for forbidden in (
        "api_key",
        "bearer ",
        "password",
        "/spaces/",
        "u-9382",
        "10.5.10.89",
    ):
        assert forbidden not in serialized
