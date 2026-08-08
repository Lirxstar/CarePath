from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.domain.models import Language
from backend.retrieval.guidelines.models import GuidelineTopic
from backend.retrieval.vector import ExternalEvidenceHit, ExternalEvidenceMetadata
from backend.storage.database import Base, create_database_engine, get_session

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")
QUESTION = (
    "I have felt more tired recently. What changed, and what is a realistic plan for this week?"
)


class DemoExternalIndex:
    def search(self, query: str, *, top_k: int = 5) -> tuple[ExternalEvidenceHit, ...]:
        del query
        hits = (
            _hit(
                "chunk-sleep",
                "src-sleep",
                GuidelineTopic.SLEEP,
                "About Sleep",
                "Sleep duration and regular sleep routines support a manageable sleep plan.",
            ),
            _hit(
                "chunk-activity",
                "src-activity",
                GuidelineTopic.PHYSICAL_ACTIVITY,
                "Adult Activity Overview",
                "Walking, steps, movement, and physical activity can be rebuilt gradually.",
            ),
            _hit(
                "chunk-stress",
                "src-stress",
                GuidelineTopic.STRESS_MANAGEMENT,
                "Managing Stress",
                "Stress and mood support can use small calming routines during high workload.",
            ),
        )
        return hits[:top_k]


def _hit(
    chunk_id: str,
    source_id: str,
    topic: GuidelineTopic,
    title: str,
    content: str,
) -> ExternalEvidenceHit:
    return ExternalEvidenceHit(
        chunk_id=chunk_id,
        score=0.99,
        content=content,
        metadata=ExternalEvidenceMetadata(
            chunk_id=chunk_id,
            source_id=source_id,
            title=title,
            canonical_url=f"https://example.test/{source_id}",
            updated_at=date(2026, 1, 1),
            retrieved_at=date(2026, 7, 30),
            language=Language.EN,
            topics=(topic,),
            organisation="Trusted public-health source",
            license="public guidance",
            source_content_hash="a" * 64,
            content_hash="b" * 64,
            ingestion_version="cp006-v1",
            embedding_model="test-embedding",
        ),
        citation=f"Trusted public-health source — {title}",
    )


@pytest.fixture
def primary_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'cp015-v06.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    application = create_app(TEST_SETTINGS)
    application.state.external_evidence_index = DemoExternalIndex()
    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _primary_package() -> tuple[dict[str, object], UUID, UUID, list[UUID]]:
    user_id = uuid4()
    goal_id = uuid4()
    plan_id = uuid4()
    interaction_id = uuid4()
    action_ids = [uuid4() for _ in range(7)]
    plan_start = datetime.now(UTC).date()
    plan_end = plan_start + timedelta(days=6)
    action_dates = tuple((plan_start + timedelta(days=offset)).isoformat() for offset in range(7))
    actions: list[dict[str, object]] = []
    for index, (action_id, action_date) in enumerate(zip(action_ids, action_dates, strict=True)):
        actions.append(
            {
                "action_id": str(action_id),
                "plan_id": str(plan_id),
                "domain": "physical_activity" if index in {1, 3, 5} else "sleep",
                "description": f"Small demo action {index + 1}",
                "frequency": f"once on {action_date}",
                "difficulty": "low",
                "rationale": "Small synthetic behaviour-support action without diagnostic claims.",
                "status": "proposed",
            }
        )

    observations: list[dict[str, object]] = []
    for day in range(1, 29):
        recent = day > 14
        timestamp = f"2026-07-{day:02d}T08:00:00+00:00"
        metrics = (
            ("sleep_duration", 6.6 if recent else 7.8, "hours"),
            ("resting_heart_rate", 68 if recent else 62, "bpm"),
            ("steps", 5100 if recent else 8200, "steps"),
            ("stress_score", 7 if recent else 4, "score_1_10"),
        )
        for metric_type, value, unit in metrics:
            observations.append(
                {
                    "observation_id": str(uuid4()),
                    "user_id": str(user_id),
                    "metric_type": metric_type,
                    "value_numeric": value,
                    "unit": unit,
                    "observed_at": timestamp,
                    "source_type": "synthetic_wearable",
                    "quality_flag": "valid",
                    "confidence": 1,
                    "metadata": {"scenario": "cp015-primary-v06"},
                }
            )

    package: dict[str, object] = {
        "profile": {
            "user_id": str(user_id),
            "age_band": "30-44",
            "preferred_language": "en",
            "timezone": "Asia/Tokyo",
            "health_goals": ["sleep", "physical_activity", "stress_mood"],
            "consent_flags": {"synthetic_demo": True},
        },
        "observations": observations,
        "journal_entries": [
            {
                "entry_id": str(uuid4()),
                "user_id": str(user_id),
                "created_at": "2026-07-24T20:00:00+09:00",
                "text": "Workload has been heavier and I have felt tired after work.",
                "language": "en",
                "user_tags": ["workload", "fatigue"],
            }
        ],
        "goals": [
            {
                "goal_id": str(goal_id),
                "user_id": str(user_id),
                "domain": "sleep",
                "description": "Restore a regular routine and manageable activity.",
                "status": "active",
                "created_at": "2026-07-30T08:00:00+09:00",
            }
        ],
        "intervention_history": {
            "plans": [
                {
                    "plan_id": str(plan_id),
                    "user_id": str(user_id),
                    "goal_id": str(goal_id),
                    "version": 1,
                    "start_date": plan_start.isoformat(),
                    "end_date": plan_end.isoformat(),
                    "status": "active",
                    "generation_interaction_id": str(interaction_id),
                }
            ],
            "actions": actions,
            "plan_feedback": [],
        },
    }
    return package, user_id, plan_id, action_ids


def _set_metric_value(package: dict[str, object], metric_type: str, value: float) -> None:
    observations = package["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        assert isinstance(observation, dict)
        if observation.get("metric_type") == metric_type:
            observation["value_numeric"] = value


def test_primary_mobile_journey_uses_v06_structured_response(primary_client: TestClient) -> None:
    package, user_id, plan_id, action_ids = _primary_package()
    imported = primary_client.post(
        "/records/import",
        json={"source_format": "json", "content": package},
    )
    assert imported.status_code == 200
    assert imported.json()["status"] == "success"

    expected_means = {
        "sleep_duration": (6.6, 7.8),
        "resting_heart_rate": (68.0, 62.0),
        "steps": (5100.0, 8200.0),
        "stress_score": (7.0, 4.0),
    }
    for metric_type, (current, baseline) in expected_means.items():
        trend = primary_client.get(
            "/records/trends",
            params={
                "user_id": str(user_id),
                "metric_type": metric_type,
                "days": 14,
                "end_date": "2026-07-28",
            },
        )
        assert trend.status_code == 200
        assert trend.json()["comparison"]["current_mean"] == pytest.approx(current)
        assert trend.json()["comparison"]["baseline_mean"] == pytest.approx(baseline)

    coached = primary_client.post(
        "/coach/message",
        json={"user_id": str(user_id), "message": QUESTION, "language": "en"},
    )
    assert coached.status_code == 200
    coach_payload = coached.json()
    assert coach_payload["status"] == "completed"
    assert coach_payload["verification_disposition"] == "pass"
    structured = coach_payload["structured_response"]
    assert structured["risk_level"] == "routine"
    assert len(structured["realistic_plan_for_this_week"]) == 7
    external_sources = [
        source for source in structured["sources"] if source["source_type"] == "external_guideline"
    ]
    assert external_sources
    assert all(source["source_id"] for source in external_sources)
    assert all(source["chunk_id"] for source in external_sources)
    assert all(source["display_citation"] for source in external_sources)

    current_plan = primary_client.get("/plans/current", params={"user_id": str(user_id)})
    assert current_plan.status_code == 200
    assert current_plan.json()["plan"]["plan_id"] == str(plan_id)
    assert len(current_plan.json()["actions"]) == 7

    feedback = primary_client.post(
        f"/plans/{plan_id}/feedback",
        json={
            "user_id": str(user_id),
            "action_id": str(action_ids[0]),
            "response": "rejected",
            "completion_ratio": 0,
            "reason_text": "Not feasible for this demo week",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["feedback"]["response"] == "rejected"

    refreshed_plan = primary_client.get("/plans/current", params={"user_id": str(user_id)})
    statuses = {item["action_id"]: item["status"] for item in refreshed_plan.json()["actions"]}
    assert statuses[str(action_ids[0])] == "rejected"

    audit = primary_client.get(f"/audit/{coach_payload['interaction_id']}")
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert [event["sequence_number"] for event in events] == list(range(1, len(events) + 1))
    assert any(event["component"] == "external_evidence_retriever" for event in events)
    assert events[-1]["component"] == "composer"


def test_modified_feedback_changes_the_next_runtime_plan(primary_client: TestClient) -> None:
    package, user_id, plan_id, action_ids = _primary_package()
    _set_metric_value(package, "stress_score", 5.0)
    imported = primary_client.post(
        "/records/import",
        json={"source_format": "json", "content": package},
    )
    assert imported.status_code == 200

    first = primary_client.post(
        "/coach/message",
        json={"user_id": str(user_id), "message": QUESTION, "language": "en"},
    )
    assert first.status_code == 200
    first_actions = first.json()["structured_response"]["realistic_plan_for_this_week"]
    assert len(first_actions) == 7
    assert all("Use 12 minutes" in action["description"] for action in first_actions)

    feedback = primary_client.post(
        f"/plans/{plan_id}/feedback",
        json={
            "user_id": str(user_id),
            "action_id": str(action_ids[0]),
            "response": "modified",
            "completion_ratio": 0.5,
            "reason_text": "Use the lighter option this week.",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["feedback"]["response"] == "modified"

    second = primary_client.post(
        "/coach/message",
        json={"user_id": str(user_id), "message": QUESTION, "language": "en"},
    )
    assert second.status_code == 200
    second_actions = second.json()["structured_response"]["realistic_plan_for_this_week"]
    assert len(second_actions) == 7
    assert all("Use 8 minutes" in action["description"] for action in second_actions)
    assert first_actions[0]["description"] != second_actions[0]["description"]