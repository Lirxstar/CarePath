from typing import Any

from evaluation.amd.validate_cp101 import validate


def _phase() -> dict[str, Any]:
    rows = [{"scenario_id": f"scenario-{index}"} for index in range(48)]
    return {
        "rows": rows,
        "metrics": {
            "success_rate": 1.0,
            "schema_compliance_rate": 1.0,
            "usage_metadata_coverage": 1.0,
            "completion_tokens_per_second": 20.0,
            "tool_selection": {"precision": 1.0, "recall": 1.0},
            "patient_context": {"precision": 1.0, "recall": 1.0},
            "external_citations": {"precision": 1.0, "recall": 1.0},
            "safety_escalation_recall": 1.0,
            "hostile_instruction_rejection_rate": 1.0,
            "response_language_accuracy": 1.0,
            "unsupported_claim_rate": 0.0,
        },
    }


def _passing_payload() -> dict[str, Any]:
    return {
        "run_mode": "local_radeon_rocm_full_cp101",
        "carepath_commit": "a" * 40,
        "provider_health": {"status": "ok", "local": True},
        "scenario_suite": {"scenario_count": 48, "sha256": "b" * 64},
        "privacy_egress_evidence": {"pass": True},
        "environment_manifest": {
            "carepath_commit": "a" * 40,
            "framework": {
                "pytorch": {
                    "accelerator_available": True,
                    "hip_version": "7.2.1",
                    "devices": [{"name": "AMD Radeon Graphics"}],
                }
            },
        },
        "resource_metrics": {
            "telemetry_available": True,
            "peak_vram_used_bytes": 1,
        },
        "baseline": _phase(),
        "optimized": _phase(),
        "comparison": {
            "behaviour_regression_detected": False,
            "throughput_gain_percent": 25.0,
            "paired_behaviour_stability_rate": 1.0,
        },
    }


def test_cp101_validator_accepts_complete_measured_bundle() -> None:
    assert validate(_passing_payload()) == []


def test_cp101_validator_rejects_remote_or_unmeasured_bundle() -> None:
    payload = _passing_payload()
    payload["provider_health"]["local"] = False
    payload["privacy_egress_evidence"]["pass"] = False
    payload["resource_metrics"]["telemetry_available"] = False
    payload["optimized"]["metrics"]["unsupported_claim_rate"] = 0.25
    payload["comparison"]["behaviour_regression_detected"] = True

    failures = validate(payload)

    assert any("local=true" in failure for failure in failures)
    assert any("privacy" in failure for failure in failures)
    assert any("telemetry" in failure for failure in failures)
    assert any("unsupported_claim_rate" in failure for failure in failures)
    assert any("regressions" in failure for failure in failures)
