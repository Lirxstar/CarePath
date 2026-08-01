from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.storage.database import Base, create_database_engine, get_session
from backend.storage.models import (
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    ObservationTable,
    PlanActionTable,
)

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'health-data-api.db'}")
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


def _profile(user_id: UUID) -> dict[str, object]:
    return {
        "user_id": str(user_id),
        "age_band": "30-44",
        "preferred_language": "en",
        "timezone": "UTC",
        "health_goals": ["sleep", "physical_activity"],
        "consent_flags": {"synthetic_data": True},
    }


def _observation(user_id: UUID, observation_id: UUID, day: int) -> dict[str, object]:
    return {
        "observation_id": str(observation_id),
        "user_id": str(user_id),
        "metric_type": "steps",
        "value_numeric": float(4000 + day * 100),
        "value_boolean": None,
        "unit": "steps",
        "observed_at": f"2026-07-{day:02d}T08:00:00+00:00",
        "source_type": "synthetic_wearable",
        "quality_flag": "valid",
        "confidence": 0.95,
        "metadata": {"day": day},
    }


def test_profile_create_and_read_round_trip(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()

    created = client.post("/profiles", json=_profile(user_id))
    read = client.get(f"/profiles/{user_id}")

    assert created.status_code == 201
    assert read.status_code == 200
    assert read.json() == created.json()


def test_observation_batch_is_atomic_and_range_read_is_paginated(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201
    observation_ids = [uuid4(), uuid4(), uuid4()]

    written = client.post(
        "/observations/batch",
        json={
            "observations": [
                _observation(user_id, observation_id, day)
                for day, observation_id in enumerate(observation_ids, start=1)
            ]
        },
    )
    assert written.status_code == 201
    assert written.json()["inserted_count"] == 3

    page = client.get(
        "/observations",
        params={
            "user_id": str(user_id),
            "start_at": "2026-07-01T00:00:00+00:00",
            "end_at": "2026-07-31T23:59:59+00:00",
            "metric_type": "steps",
            "limit": 2,
            "offset": 1,
        },
    )
    assert page.status_code == 200
    payload = page.json()
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert payload["returned_count"] == 2
    assert [item["observation_id"] for item in payload["items"]] == [
        str(observation_ids[1]),
        str(observation_ids[2]),
    ]

    duplicate = client.post(
        "/observations/batch",
        json={"observations": [_observation(user_id, observation_ids[0], 4)]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "observation_exists"
    with factory() as session:
        assert len(session.scalars(select(ObservationTable)).all()) == 3


def test_observation_validation_rejects_wrong_unit_illegal_value_and_missing_user(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201

    wrong_unit = _observation(user_id, uuid4(), 1)
    wrong_unit["unit"] = "hours"
    response = client.post("/observations/batch", json={"observations": [wrong_unit]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    illegal_steps = _observation(user_id, uuid4(), 1)
    illegal_steps["value_numeric"] = -1
    response = client.post("/observations/batch", json={"observations": [illegal_steps]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    missing_user_observation = _observation(uuid4(), uuid4(), 1)
    response = client.post(
        "/observations/batch",
        json={"observations": [missing_user_observation]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"
    with factory() as session:
        assert session.scalars(select(ObservationTable)).all() == []


def test_observation_range_limits_return_controlled_4xx(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201

    reversed_range = client.get(
        "/observations",
        params={
            "user_id": str(user_id),
            "start_at": "2026-07-02T00:00:00+00:00",
            "end_at": "2026-07-01T00:00:00+00:00",
        },
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["error"]["code"] == "invalid_date_range"

    oversized_range = client.get(
        "/observations",
        params={
            "user_id": str(user_id),
            "start_at": "2025-01-01T00:00:00+00:00",
            "end_at": "2026-07-01T00:00:00+00:00",
        },
    )
    assert oversized_range.status_code == 422
    assert oversized_range.json()["error"]["code"] == "date_range_too_large"

    timezone_missing = client.get(
        "/observations",
        params={
            "user_id": str(user_id),
            "start_at": "2026-07-01T00:00:00",
            "end_at": "2026-07-02T00:00:00",
        },
    )
    assert timezone_missing.status_code == 422
    assert timezone_missing.json()["error"]["code"] == "timezone_required"

    invalid_page = client.get(
        "/observations",
        params={
            "user_id": str(user_id),
            "start_at": "2026-07-01T00:00:00+00:00",
            "end_at": "2026-07-02T00:00:00+00:00",
            "limit": 101,
        },
    )
    assert invalid_page.status_code == 422
    assert invalid_page.json()["error"]["code"] == "validation_error"


def test_journal_and_goal_creation_validate_profile_and_duplicates(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201

    journal = {
        "entry_id": str(uuid4()),
        "user_id": str(user_id),
        "created_at": "2026-07-30T08:00:00+00:00",
        "text": "A synthetic journal check-in.",
        "language": "en",
        "user_tags": ["synthetic"],
    }
    assert client.post("/journals", json=journal).status_code == 201
    duplicate_journal = client.post("/journals", json=journal)
    assert duplicate_journal.status_code == 409
    assert duplicate_journal.json()["error"]["code"] == "journal_entry_exists"

    goal = {
        "goal_id": str(uuid4()),
        "user_id": str(user_id),
        "domain": "sleep",
        "description": "Keep a regular sleep schedule",
        "status": "active",
        "created_at": "2026-07-30T08:00:00+00:00",
        "target_date": "2026-08-30",
    }
    assert client.post("/goals", json=goal).status_code == 201
    duplicate_goal = client.post("/goals", json=goal)
    assert duplicate_goal.status_code == 409
    assert duplicate_goal.json()["error"]["code"] == "goal_exists"

    missing_user_goal = dict(goal)
    missing_user_goal["goal_id"] = str(uuid4())
    missing_user_goal["user_id"] = str(uuid4())
    response = client.post("/goals", json=missing_user_goal)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


def test_plan_history_returns_versions_with_actions_and_pagination(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    user_id = uuid4()
    goal_id = uuid4()
    interaction_id = uuid4()
    older_plan_id = uuid4()
    newer_plan_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201

    with factory() as session:
        session.add(
            GoalTable(
                goal_id=str(goal_id),
                user_id=str(user_id),
                domain="sleep",
                description="Regular sleep",
                status="active",
                created_at=datetime(2026, 7, 1, tzinfo=UTC),
                target_date=None,
            )
        )
        session.add(
            InteractionTable(
                interaction_id=str(interaction_id),
                user_id=str(user_id),
                request_text="Generate plans",
                language="en",
                started_at=datetime(2026, 7, 1, tzinfo=UTC),
                completed_at=datetime(2026, 7, 1, tzinfo=UTC),
                risk_level="routine",
                final_status="completed",
                response_json={},
            )
        )
        session.flush()
        session.add_all(
            [
                InterventionPlanTable(
                    plan_id=str(older_plan_id),
                    user_id=str(user_id),
                    goal_id=str(goal_id),
                    version=1,
                    start_date=date(2026, 7, 1),
                    end_date=date(2026, 7, 7),
                    status="superseded",
                    generation_interaction_id=str(interaction_id),
                    supersedes_plan_id=None,
                ),
                InterventionPlanTable(
                    plan_id=str(newer_plan_id),
                    user_id=str(user_id),
                    goal_id=str(goal_id),
                    version=2,
                    start_date=date(2026, 7, 8),
                    end_date=date(2026, 7, 14),
                    status="active",
                    generation_interaction_id=str(interaction_id),
                    supersedes_plan_id=str(older_plan_id),
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PlanActionTable(
                    action_id=str(uuid4()),
                    plan_id=str(older_plan_id),
                    domain="sleep",
                    description="Older action",
                    frequency="daily",
                    difficulty="medium",
                    rationale="Historical action",
                    status="completed",
                ),
                PlanActionTable(
                    action_id=str(uuid4()),
                    plan_id=str(newer_plan_id),
                    domain="sleep",
                    description="Newer action",
                    frequency="daily",
                    difficulty="low",
                    rationale="Current action",
                    status="accepted",
                ),
            ]
        )
        session.commit()

    history = client.get(
        "/plans/history",
        params={"user_id": str(user_id), "limit": 1, "offset": 0},
    )
    assert history.status_code == 200
    assert history.json()["returned_count"] == 1
    assert history.json()["items"][0]["plan"]["plan_id"] == str(newer_plan_id)
    assert history.json()["items"][0]["actions"][0]["description"] == "Newer action"

    older_page = client.get(
        "/plans/history",
        params={"user_id": str(user_id), "limit": 1, "offset": 1},
    )
    assert older_page.status_code == 200
    assert older_page.json()["items"][0]["plan"]["plan_id"] == str(older_plan_id)


def test_openapi_includes_health_data_crud_surface(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    document = client.get("/openapi.json").json()
    required = {
        "/profiles/{user_id}": "get",
        "/observations/batch": "post",
        "/observations": "get",
        "/journals": "post",
        "/goals": "post",
        "/plans/history": "get",
    }
    for path, method in required.items():
        assert path in document["paths"]
        assert method in document["paths"][path]
