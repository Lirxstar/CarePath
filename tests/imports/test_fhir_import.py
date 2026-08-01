import json
from pathlib import Path

from backend.imports.fhir import FHIRBundleImporter

FIXTURES = Path(__file__).parents[2] / "data" / "examples" / "fhir"


def load_bundle(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def encode_bundle(entries: list[object]) -> bytes:
    return json.dumps({"resourceType": "Bundle", "type": "collection", "entry": entries}).encode()


def patient(resource_id: str = "p1") -> dict[str, object]:
    return {"resourceType": "Patient", "id": resource_id, "birthDate": "1990-01-01"}


def test_valid_bundle_maps_supported_resources() -> None:
    result = FHIRBundleImporter().prepare(load_bundle("valid_bundle.json"))

    assert result.report.status == "success"
    assert len(result.user_profiles) == 1
    assert len(result.observations) == 1
    assert len(result.goals) == 1
    assert len(result.intervention_plans) == 1
    assert len(result.plan_actions) == 1
    assert len(result.interactions) == 1


def test_unknown_observation_code_preserves_original_value() -> None:
    result = FHIRBundleImporter().prepare(load_bundle("unknown_code_bundle.json"))

    assert result.report.status == "partial"
    issue = next(
        item for item in result.report.skipped_records if item.code == "unknown_observation_code"
    )
    assert issue.original_value == "vendor_metric_x"
    assert result.observations == []


def test_unsupported_resource_is_skipped_without_crashing() -> None:
    result = FHIRBundleImporter().prepare(load_bundle("unsupported_resource_bundle.json"))

    assert result.report.status == "partial"
    issue = result.report.skipped_records[0]
    assert issue.code == "unsupported_resource_skipped"
    assert issue.resource_type == "MedicationRequest"
    assert result.report.blocking_errors == []


def test_broken_patient_reference_is_reported_and_skipped() -> None:
    result = FHIRBundleImporter().prepare(load_bundle("invalid_reference_bundle.json"))

    assert result.report.status == "partial"
    assert result.observations == []
    assert any(
        item.code == "invalid_resource" and item.resource_type == "Observation"
        for item in result.report.skipped_records
    )


def test_invalid_json_and_non_bundle_are_blocking() -> None:
    invalid_json = FHIRBundleImporter().prepare(b"{broken")
    non_bundle = FHIRBundleImporter().prepare(b'{"resourceType":"Observation"}')

    assert invalid_json.report.status == "failed"
    assert invalid_json.report.blocking_errors[0].code == "invalid_bundle"
    assert non_bundle.report.status == "failed"
    assert non_bundle.report.blocking_errors[0].code == "not_bundle"


def test_bundle_entry_must_be_list() -> None:
    result = FHIRBundleImporter().prepare(b'{"resourceType":"Bundle","entry":{}}')

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_entries"


def test_invalid_entry_and_supported_resource_without_id_are_explicitly_skipped() -> None:
    result = FHIRBundleImporter().prepare(
        encode_bundle(
            [
                {"not_resource": {}},
                {"resource": {"resourceType": "Patient", "birthDate": "1990-01-01"}},
            ]
        )
    )

    assert result.report.status == "partial"
    assert [item.code for item in result.report.skipped_records] == [
        "invalid_entry",
        "missing_resource_id",
    ]


def test_patient_defaults_language_and_timezone_as_repairable_issues() -> None:
    result = FHIRBundleImporter().prepare(encode_bundle([{"resource": patient()}]))

    assert result.report.status == "success"
    assert len(result.user_profiles) == 1
    assert {item.code for item in result.report.fixed_issues} == {
        "language_defaulted",
        "timezone_defaulted",
    }


def test_underage_patient_is_skipped_as_invalid_resource() -> None:
    child = {"resourceType": "Patient", "id": "child", "birthDate": "2015-01-01"}
    result = FHIRBundleImporter().prepare(encode_bundle([{"resource": child}]))

    assert result.report.status == "partial"
    assert result.user_profiles == []
    assert result.report.skipped_records[0].code == "invalid_resource"


def test_boolean_event_observation_maps_without_unit() -> None:
    observation = {
        "resourceType": "Observation",
        "id": "fall-1",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"code": "fall_event"}]},
        "valueBoolean": True,
        "effectiveDateTime": "2026-07-28T08:00:00+09:00",
    }
    result = FHIRBundleImporter().prepare(
        encode_bundle([{"resource": patient()}, {"resource": observation}])
    )

    assert result.report.status == "success"
    assert result.observations[0]["value_boolean"] is True
    assert result.observations[0]["unit"] is None


def test_bad_observation_unit_is_reported_as_invalid_resource() -> None:
    observation = {
        "resourceType": "Observation",
        "id": "steps-bad-unit",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"code": "steps"}]},
        "valueQuantity": {"value": 1000, "unit": "kilograms"},
        "effectiveDateTime": "2026-07-28T08:00:00+09:00",
    }
    result = FHIRBundleImporter().prepare(
        encode_bundle([{"resource": patient()}, {"resource": observation}])
    )

    assert result.report.status == "partial"
    assert result.observations == []
    assert any(item.code == "invalid_resource" for item in result.report.skipped_records)


def test_unknown_goal_domain_is_preserved_and_skipped() -> None:
    goal = {
        "resourceType": "Goal",
        "id": "goal-unknown",
        "subject": {"reference": "Patient/p1"},
        "lifecycleStatus": "active",
        "category": [{"coding": [{"system": "vendor", "code": "nutrition"}]}],
        "description": {"text": "Eat differently"},
    }
    result = FHIRBundleImporter().prepare(
        encode_bundle([{"resource": patient()}, {"resource": goal}])
    )

    assert result.report.status == "partial"
    issue = next(
        item for item in result.report.skipped_records if item.code == "unknown_goal_domain"
    )
    assert issue.original_value == "nutrition"
    assert result.goals == []


def test_careplan_missing_period_is_skipped_without_partial_plan() -> None:
    goal = {
        "resourceType": "Goal",
        "id": "g1",
        "subject": {"reference": "Patient/p1"},
        "lifecycleStatus": "active",
        "category": [{"coding": [{"code": "physical_activity"}]}],
        "description": {"text": "Walk more"},
    }
    careplan = {
        "resourceType": "CarePlan",
        "id": "cp1",
        "subject": {"reference": "Patient/p1"},
        "status": "active",
        "addresses": [{"reference": "Goal/g1"}],
    }
    result = FHIRBundleImporter().prepare(
        encode_bundle(
            [
                {"resource": patient()},
                {"resource": goal},
                {"resource": careplan},
            ]
        )
    )

    assert result.report.status == "partial"
    assert result.intervention_plans == []
    assert result.plan_actions == []
    assert any(
        item.code == "invalid_resource" and item.resource_type == "CarePlan"
        for item in result.report.skipped_records
    )
