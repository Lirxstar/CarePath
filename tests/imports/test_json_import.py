import json

from backend.imports.json_importer import JSONHealthImporter

USER_ID = "22222222-2222-2222-2222-222222222222"
GOAL_ID = "33333333-3333-3333-3333-333333333333"
PLAN_ID = "44444444-4444-4444-4444-444444444444"
INTERACTION_ID = "55555555-5555-5555-5555-555555555555"


def profile(language: str = "en") -> dict[str, object]:
    return {
        "user_id": USER_ID,
        "age_band": "30-44",
        "preferred_language": language,
        "timezone": "Asia/Tokyo",
        "health_goals": [],
        "consent_flags": {},
    }


def test_invalid_collection_is_blocking() -> None:
    result = JSONHealthImporter().prepare(
        json.dumps({"observations": {"unexpected": "object"}}).encode()
    )

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_collection"
    assert result.observations == []


def test_profile_single_object_is_supported() -> None:
    result = JSONHealthImporter().prepare(json.dumps({"profile": profile()}).encode())

    assert result.report.status == "success"
    assert len(result.user_profiles) == 1


def test_invalid_json_is_blocking() -> None:
    result = JSONHealthImporter().prepare(b"{not-json")

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_json"


def test_non_object_root_is_blocking() -> None:
    result = JSONHealthImporter().prepare(b"[]")

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_package"


def test_invalid_intervention_history_shape_is_blocking() -> None:
    result = JSONHealthImporter().prepare(
        json.dumps({"profile": profile(), "intervention_history": []}).encode()
    )

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_intervention_history"


def test_invalid_record_is_skipped_explicitly() -> None:
    result = JSONHealthImporter().prepare(
        json.dumps(
            {
                "profile": profile(),
                "goals": [
                    {
                        "goal_id": GOAL_ID,
                        "user_id": USER_ID,
                        "domain": "not-a-domain",
                        "description": "invalid goal",
                        "status": "active",
                        "created_at": "2026-07-28T08:00:00+09:00",
                    }
                ],
            }
        ).encode()
    )

    assert result.report.status == "partial"
    assert result.report.skipped_records[0].resource_type == "Goal"
    assert result.goals == []


def test_plan_import_synthesizes_typed_provenance_interaction() -> None:
    payload = {
        "profile": profile("ja"),
        "goals": [
            {
                "goal_id": GOAL_ID,
                "user_id": USER_ID,
                "domain": "physical_activity",
                "description": "Walk more",
                "status": "active",
                "created_at": "2026-07-28T08:00:00+09:00",
            }
        ],
        "intervention_history": {
            "plans": [
                {
                    "plan_id": PLAN_ID,
                    "user_id": USER_ID,
                    "goal_id": GOAL_ID,
                    "version": 1,
                    "start_date": "2026-07-28",
                    "end_date": "2026-08-03",
                    "status": "active",
                    "generation_interaction_id": INTERACTION_ID,
                }
            ]
        },
    }

    result = JSONHealthImporter().prepare(json.dumps(payload).encode())

    assert result.report.status == "success"
    assert len(result.intervention_plans) == 1
    assert len(result.interactions) == 1
    assert str(result.interactions[0]["interaction_id"]) == INTERACTION_ID
    assert result.interactions[0]["language"] == "ja"
