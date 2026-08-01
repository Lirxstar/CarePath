from __future__ import annotations

import csv
import io
from collections.abc import Generator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.storage.database import Base, create_database_engine, get_session
from backend.storage.models import (
    AuditEventTable,
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    PlanActionTable,
)

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'cp012.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    application = create_app(TEST_SETTINGS)
    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            yield client, factory
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _profile_payload(user_id: UUID) -> dict[str, object]:
    return {
        "user_id": str(user_id),
        "age_band": "30-44",
        "preferred_language": "en",
        "timezone": "UTC",
        "health_goals": ["sleep", "physical_activity"],
        "consent_flags": {"demo": True},
    }


def _csv_observations(user_id: UUID) -> str:
    fieldnames = [
        "observation_id",
        "user_id",
        "metric_type",
        "value_numeric",
        "value_boolean",
        "unit",
        "observed_at",
        "source_type",
        "quality_flag",
        "confidence",
        "metadata",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for day_number in range(1, 15):
        writer.writerow(
            {
                "observation_id": str(uuid4()),
                "user_id": str(user_id),
                "metric_type": "sleep_duration",
                "value_numeric": "8" if day_number <= 7 else "7",
                "value_boolean": "",
                "unit": "hours",
                "observed_at": f"2026-07-{day_number:02d}T12:00:00+00:00",
                "source_type": "synthetic_wearable",
                "quality_flag": "valid",
                "confidence": "1",
                "metadata": "",
            }
        )
    return buffer.getvalue()


def test_openapi_contains_every_frozen_endpoint(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    document = client.get("/openapi.json").json()
    required = {
        "/profiles": "post",
        "/records/import": "post",
        "/fhir/bundle": "post",
        "/records/trends": "get",
        "/coach/message": "post",
        "/plans/current": "get",
        "/plans/{plan_id}/feedback": "post",
        "/audit/{interaction_id}": "get",
        "/health": "get",
    }

    for path, method in required.items():
        assert path in document["paths"]
        assert method in document["paths"][path]

    assert document["paths"]["/profiles"]["post"]["requestBody"]["required"] is True
    assert document["paths"]["/coach/message"]["post"]["requestBody"]["required"] is True


def test_profile_validation_request_id_and_duplicate_error(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()

    invalid = client.post(
        "/profiles",
        json={},
        headers={"X-Request-ID": "profile-validation"},
    )
    assert invalid.status_code == 422
    assert invalid.headers["X-Request-ID"] == "profile-validation"
    assert invalid.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed",
            "request_id": "profile-validation",
        }
    }

    created = client.post(
        "/profiles",
        json=_profile_payload(user_id),
        headers={"X-Request-ID": "profile-create"},
    )
    assert created.status_code == 201
    assert created.headers["X-Request-ID"] == "profile-create"
    assert created.json()["user_id"] == str(user_id)

    duplicate = client.post("/profiles", json=_profile_payload(user_id))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "profile_exists"
    assert duplicate.json()["error"]["request_id"]


def test_records_import_supports_csv_json_and_trend_analysis(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile_payload(user_id)).status_code == 201

    csv_response = client.post(
        "/records/import",
        json={"source_format": "csv", "content": _csv_observations(user_id)},
    )
    assert csv_response.status_code == 200
    assert csv_response.json()["status"] == "success"
    assert csv_response.json()["inserted_records"] == 14

    json_user_id = uuid4()
    json_response = client.post(
        "/records/import",
        json={
            "source_format": "json",
            "content": {
                "profile": _profile_payload(json_user_id),
                "observations": [],
                "journal_entries": [],
                "goals": [],
                "intervention_history": {
                    "plans": [],
                    "actions": [],
                    "plan_feedback": [],
                },
            },
        },
    )
    assert json_response.status_code == 200
    assert json_response.json()["status"] == "success"
    assert json_response.json()["inserted_records"] == 1

    trends = client.get(
        "/records/trends",
        params={
            "user_id": str(user_id),
            "metric_type": "sleep_duration",
            "days": 7,
            "end_date": date(2026, 7, 14).isoformat(),
        },
    )
    assert trends.status_code == 200
    payload = trends.json()
    assert payload["trend"]["mean"] == pytest.approx(7.0)
    assert payload["comparison"]["current_mean"] == pytest.approx(7.0)
    assert payload["comparison"]["baseline_mean"] == pytest.approx(8.0)
    assert len(payload["trend"]["source_observation_ids"]) == 7


def test_fhir_bundle_uses_typed_bundle_contract(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    response = client.post(
        "/fhir/bundle",
        json={
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "demo-patient",
                        "birthDate": "1990-01-01",
                    }
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["inserted_records"] == 1

    invalid = client.post("/fhir/bundle", json={"resourceType": "Patient", "entry": []})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_coach_message_returns_interaction_id_and_persists_interaction(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile_payload(user_id)).status_code == 201

    response = client.post(
        "/coach/message",
        json={
            "user_id": str(user_id),
            "message": "Help me make my sleep schedule more regular",
            "language": "en",
        },
        headers={"X-Request-ID": "coach-contract-id"},
    )
    assert response.status_code == 200
    payload = response.json()
    interaction_id = UUID(payload["interaction_id"])
    assert payload["request_id"] == "coach-contract-id"
    assert payload["risk_level"] == "routine"
    assert payload["status"] == "completed"
    assert payload["verification_disposition"] == "pass"
    assert response.headers["X-Request-ID"] == "coach-contract-id"

    with factory() as session:
        row = session.get(InteractionTable, str(interaction_id))
        assert row is not None
        assert row.user_id == str(user_id)
        assert row.final_status == "completed"

    audit = client.get(f"/audit/{interaction_id}")
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert [event["sequence_number"] for event in events] == list(range(1, len(events) + 1))
    event_types = [event["event_type"] for event in events]
    assert event_types[0] == "safety_decision"
    assert event_types.count("tool_call") == 4
    assert event_types.count("tool_result") == 4
    assert event_types.count("retrieval") == 2
    assert event_types[-3:] == ["plan_generated", "verification", "response_emitted"]


def test_current_plan_feedback_and_ordered_audit_trace(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    user_id = uuid4()
    goal_id = uuid4()
    interaction_id = uuid4()
    plan_id = uuid4()
    action_id = uuid4()
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)

    assert client.post("/profiles", json=_profile_payload(user_id)).status_code == 201
    with factory() as session:
        session.add(
            GoalTable(
                goal_id=str(goal_id),
                user_id=str(user_id),
                domain="sleep",
                description="Regular sleep routine",
                status="active",
                created_at=now,
                target_date=None,
            )
        )
        session.add(
            InteractionTable(
                interaction_id=str(interaction_id),
                user_id=str(user_id),
                request_text="Generate a plan",
                language="en",
                started_at=now,
                completed_at=now,
                risk_level="routine",
                final_status="completed",
                response_json={},
            )
        )
        session.flush()
        session.add(
            InterventionPlanTable(
                plan_id=str(plan_id),
                user_id=str(user_id),
                goal_id=str(goal_id),
                version=1,
                start_date=date(2026, 7, 30),
                end_date=date(2026, 8, 5),
                status="active",
                generation_interaction_id=str(interaction_id),
                supersedes_plan_id=None,
            )
        )
        session.flush()
        session.add(
            PlanActionTable(
                action_id=str(action_id),
                plan_id=str(plan_id),
                domain="sleep",
                description="Keep a regular bedtime",
                frequency="once on 2026-07-30",
                difficulty="low",
                rationale="Supports the current sleep goal",
                status="proposed",
            )
        )
        session.add_all(
            [
                AuditEventTable(
                    audit_event_id=str(uuid4()),
                    interaction_id=str(interaction_id),
                    sequence_number=2,
                    event_type="verification",
                    component="verifier",
                    input_refs={"draft": "draft-1"},
                    output_summary={"status": "pass"},
                    created_at=now,
                ),
                AuditEventTable(
                    audit_event_id=str(uuid4()),
                    interaction_id=str(interaction_id),
                    sequence_number=1,
                    event_type="safety_decision",
                    component="safety_triage",
                    input_refs={},
                    output_summary={"risk_level": "routine"},
                    created_at=now,
                ),
            ]
        )
        session.commit()

    current = client.get("/plans/current", params={"user_id": str(user_id)})
    assert current.status_code == 200
    assert current.json()["plan"]["plan_id"] == str(plan_id)
    assert current.json()["actions"][0]["action_id"] == str(action_id)

    feedback = client.post(
        f"/plans/{plan_id}/feedback",
        json={
            "user_id": str(user_id),
            "action_id": str(action_id),
            "response": "rejected",
            "completion_ratio": 0,
            "reason_text": "Not feasible this week",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["plan_id"] == str(plan_id)
    assert feedback.json()["feedback"]["response"] == "rejected"

    with factory() as session:
        action = session.get(PlanActionTable, str(action_id))
        assert action is not None
        assert action.status == "rejected"

    audit = client.get(f"/audit/{interaction_id}")
    assert audit.status_code == 200
    assert [event["sequence_number"] for event in audit.json()["events"]] == [1, 2]


def test_endpoint_errors_are_structured_and_do_not_expose_internal_details(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    missing_user = uuid4()

    trend = client.get(
        "/records/trends",
        params={"user_id": str(missing_user), "metric_type": "steps"},
        headers={"X-Request-ID": "missing-records"},
    )
    assert trend.status_code == 404
    assert trend.json()["error"] == {
        "code": "records_not_found",
        "message": "No observations were found for this user and metric",
        "request_id": "missing-records",
    }

    invalid_days = client.get(
        "/records/trends",
        params={"user_id": str(missing_user), "metric_type": "steps", "days": 0},
    )
    assert invalid_days.status_code == 422
    assert invalid_days.json()["error"]["code"] == "validation_error"

    coach = client.post(
        "/coach/message",
        json={"user_id": str(missing_user), "message": "Help me sleep", "language": "en"},
    )
    assert coach.status_code == 404
    assert coach.json()["error"]["code"] == "profile_not_found"
