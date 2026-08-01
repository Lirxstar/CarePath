from __future__ import annotations

import csv
import json
import re
from collections.abc import Generator
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.domain import Goal, InterventionPlan, PlanAction, PlanFeedback, UserProfile
from backend.personalization.analysis import build_personalization_summary, summarise_adherence
from backend.storage.database import Base, create_database_engine, get_session
from data.synthetic.generate import _parse_csv_row, generate

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


@pytest.fixture
def gate_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'backend-gate.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    application = create_app(TEST_SETTINGS)
    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _load_generated(output: Path) -> dict[str, object]:
    profiles = json.loads((output / "profile.json").read_text(encoding="utf-8"))
    journals = json.loads((output / "journal_entries.json").read_text(encoding="utf-8"))
    goals = json.loads((output / "goals.json").read_text(encoding="utf-8"))
    history = json.loads((output / "intervention_history.json").read_text(encoding="utf-8"))
    observations: list[dict[str, object]] = []
    with (output / "observations.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            observations.append(_parse_csv_row(row))
    return {
        "profiles": profiles,
        "journals": journals,
        "goals": goals,
        "history": history,
        "observations": observations,
    }


def _persona_payload(dataset: dict[str, object], profile: dict[str, object]) -> dict[str, object]:
    user_id = str(profile["user_id"])
    history = dataset["history"]
    assert isinstance(history, dict)
    plans = [item for item in history["plans"] if str(item["user_id"]) == user_id]
    plan_ids = {str(item["plan_id"]) for item in plans}
    actions = [item for item in history["actions"] if str(item["plan_id"]) in plan_ids]
    action_ids = {str(item["action_id"]) for item in actions}
    feedback = [item for item in history["plan_feedback"] if str(item["action_id"]) in action_ids]
    return {
        "profile": profile,
        "observations": [
            item for item in dataset["observations"] if str(item["user_id"]) == user_id
        ],
        "journal_entries": [
            item for item in dataset["journals"] if str(item["user_id"]) == user_id
        ],
        "goals": [item for item in dataset["goals"] if str(item["user_id"]) == user_id],
        "intervention_history": {
            "plans": plans,
            "actions": actions,
            "plan_feedback": feedback,
        },
    }


def test_ten_synthetic_personas_import_and_read_through_public_api(
    gate_client: TestClient,
    tmp_path: Path,
) -> None:
    output = tmp_path / "synthetic"
    generate(seed=42, days=30, output=output)
    dataset = _load_generated(output)
    profiles = dataset["profiles"]
    assert isinstance(profiles, list)
    assert len(profiles) == 10

    for profile in profiles:
        assert isinstance(profile, dict)
        user_id = UUID(str(profile["user_id"]))
        payload = _persona_payload(dataset, profile)
        imported = gate_client.post(
            "/records/import",
            json={"source_format": "json", "content": payload},
        )
        assert imported.status_code == 200
        assert imported.json()["status"] == "success"
        assert imported.json()["inserted_records"] > 0

        profile_response = gate_client.get(f"/profiles/{user_id}")
        assert profile_response.status_code == 200
        assert profile_response.json()["user_id"] == str(user_id)

        observations = gate_client.get(
            "/observations",
            params={
                "user_id": str(user_id),
                "start_at": "2026-01-01T00:00:00+00:00",
                "end_at": "2026-01-30T23:59:59+00:00",
                "limit": 100,
            },
        )
        assert observations.status_code == 200
        assert observations.json()["returned_count"] == 100

        trends = gate_client.get(
            "/records/trends",
            params={
                "user_id": str(user_id),
                "metric_type": "steps",
                "days": 7,
                "end_date": date(2026, 1, 30).isoformat(),
            },
        )
        assert trends.status_code == 200
        assert trends.json()["trend"]["source_observation_ids"]

        history = gate_client.get(
            "/plans/history",
            params={"user_id": str(user_id)},
        )
        assert history.status_code == 200
        assert history.json()["returned_count"] == 1
        assert len(history.json()["items"][0]["actions"]) == 4

    health = gate_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_generated_personas_feed_personalization_tool_contract(tmp_path: Path) -> None:
    output = tmp_path / "synthetic-personalization"
    generate(seed=91, days=30, output=output)
    dataset = _load_generated(output)
    profiles = dataset["profiles"]
    assert isinstance(profiles, list)

    for raw_profile in profiles:
        assert isinstance(raw_profile, dict)
        payload = _persona_payload(dataset, raw_profile)
        history = payload["intervention_history"]
        assert isinstance(history, dict)
        profile = UserProfile.model_validate(raw_profile)
        goals = [Goal.model_validate(item) for item in payload["goals"]]
        plans = [InterventionPlan.model_validate(item) for item in history["plans"]]
        actions = [PlanAction.model_validate(item) for item in history["actions"]]
        feedback = [PlanFeedback.model_validate(item) for item in history["plan_feedback"]]
        adherence = summarise_adherence(actions, feedback, plans)
        summary = build_personalization_summary(profile, goals, plans, adherence)

        assert summary.source_plan_ids
        assert summary.source_action_ids
        assert summary.source_feedback_ids
        assert summary.difficulty_signal.recommended_difficulty_direction.value in {
            "reduce",
            "maintain",
            "increase",
        }


def test_backend_gate_has_no_blocking_todos_or_user_specific_absolute_paths() -> None:
    backend_root = Path(__file__).resolve().parents[1] / "backend"
    blocking_todo = re.compile(r"(?i)\b(?:TODO|FIXME)\b.*\b(?:blocking|blocker)\b")
    forbidden_paths = ("/Users/", "C:\\Users\\", "/home/")
    violations: list[str] = []

    for path in backend_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if blocking_todo.search(text):
            violations.append(f"blocking TODO in {path.relative_to(backend_root)}")
        for marker in forbidden_paths:
            if marker in text:
                violations.append(
                    f"user-specific absolute path {marker!r} in {path.relative_to(backend_root)}"
                )

    assert violations == []
