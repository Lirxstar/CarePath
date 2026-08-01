from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.retrieval import (
    PatientEvidenceKind,
    PatientEvidenceQuery,
    PatientEvidenceService,
)
from backend.storage.models import (
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    UserProfileTable,
)


def _seed_user(session: Session, *, user_id: str, label: str) -> dict[str, list[str] | str]:
    session.add(
        UserProfileTable(
            user_id=user_id,
            age_band="30-44",
            preferred_language="en",
            timezone="UTC",
            schedule_constraints={"weekday_evening_minutes": 20},
            health_goals=["sleep", "physical_activity"],
            activity_constraints=None,
            coaching_preferences={"style": "brief"},
            consent_flags={"demo": True},
        )
    )
    session.flush()
    observation_ids: list[str] = []
    start = datetime(2026, 7, 1, 8, tzinfo=UTC)
    for index in range(10):
        observed_at = start + timedelta(days=index)
        steps_id = str(uuid4())
        sleep_id = str(uuid4())
        observation_ids.extend([steps_id, sleep_id])
        session.add_all(
            [
                ObservationTable(
                    observation_id=steps_id,
                    user_id=user_id,
                    metric_type="steps",
                    value_numeric=float(4000 + index * 100),
                    value_boolean=None,
                    unit="steps",
                    observed_at=observed_at,
                    source_type="synthetic_wearable",
                    quality_flag="valid",
                    confidence=0.95,
                    metadata_json={"label": label},
                ),
                ObservationTable(
                    observation_id=sleep_id,
                    user_id=user_id,
                    metric_type="sleep_duration",
                    value_numeric=6.0 + index * 0.1,
                    value_boolean=None,
                    unit="hours",
                    observed_at=observed_at,
                    source_type="synthetic_wearable",
                    quality_flag="valid",
                    confidence=0.95,
                    metadata_json={"label": label},
                ),
            ]
        )

    journal_id = str(uuid4())
    session.add(
        JournalEntryTable(
            entry_id=journal_id,
            user_id=user_id,
            created_at=datetime(2026, 7, 9, 20, tzinfo=UTC),
            text=f"{label} sleep felt irregular after a late evening.",
            language="en",
            user_tags=["sleep"],
        )
    )
    goal_id = str(uuid4())
    session.add(
        GoalTable(
            goal_id=goal_id,
            user_id=user_id,
            domain="physical_activity",
            description=f"{label} walk after lunch",
            status="active",
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
            target_date=date(2026, 7, 31),
        )
    )
    interaction_id = str(uuid4())
    session.add(
        InteractionTable(
            interaction_id=interaction_id,
            user_id=user_id,
            request_text="seed plan",
            language="en",
            started_at=datetime(2026, 7, 1, tzinfo=UTC),
            completed_at=datetime(2026, 7, 1, tzinfo=UTC),
            risk_level="routine",
            final_status="completed",
            response_json={"seed": True},
        )
    )
    plan_id = str(uuid4())
    session.add(
        InterventionPlanTable(
            plan_id=plan_id,
            user_id=user_id,
            goal_id=goal_id,
            version=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 14),
            status="active",
            generation_interaction_id=interaction_id,
            supersedes_plan_id=None,
        )
    )
    action_id = str(uuid4())
    session.add(
        PlanActionTable(
            action_id=action_id,
            plan_id=plan_id,
            domain="physical_activity",
            description=f"{label} take a short walk after lunch",
            frequency="daily",
            difficulty="low",
            rationale="seed",
            status="accepted",
        )
    )
    session.flush()
    return {
        "observation_ids": observation_ids,
        "journal_id": journal_id,
        "goal_id": goal_id,
        "plan_id": plan_id,
        "action_id": action_id,
    }


def test_patient_evidence_is_user_scoped_and_distinguishes_subjective_text(
    database_session: Session,
) -> None:
    user_a = str(uuid4())
    user_b = str(uuid4())
    ids_a = _seed_user(database_session, user_id=user_a, label="USER_A")
    ids_b = _seed_user(database_session, user_id=user_b, label="USER_B_PRIVATE")

    result = PatientEvidenceService(database_session).retrieve(
        PatientEvidenceQuery(
            user_id=user_a,
            window_days=7,
            end_at=datetime(2026, 7, 10, 23, tzinfo=UTC),
            metric_types=("steps",),
            keyword="sleep",
        )
    )

    serialized = result.model_dump_json()
    assert "USER_A sleep felt irregular" in serialized
    assert "USER_B_PRIVATE" not in serialized
    assert str(ids_b["journal_id"]) not in serialized
    assert any(item.kind is PatientEvidenceKind.STRUCTURED_FACT for item in result.items)
    assert any(item.kind is PatientEvidenceKind.SUBJECTIVE_DESCRIPTION for item in result.items)
    assert set(ids_a["observation_ids"]).intersection(
        record_id for item in result.structured_facts for record_id in item.source_record_ids
    )


def test_patient_evidence_supports_30_day_and_explicit_ranges(database_session: Session) -> None:
    user_id = str(uuid4())
    ids = _seed_user(database_session, user_id=user_id, label="RANGE_USER")
    service = PatientEvidenceService(database_session)

    thirty_day = service.retrieve(
        PatientEvidenceQuery(
            user_id=user_id,
            window_days=30,
            end_at=datetime(2026, 7, 10, 23, tzinfo=UTC),
            metric_types=("sleep_duration",),
        )
    )
    custom = service.retrieve(
        PatientEvidenceQuery(
            user_id=user_id,
            window_days=None,
            start_at=datetime(2026, 7, 4, tzinfo=UTC),
            end_at=datetime(2026, 7, 6, 23, tzinfo=UTC),
            metric_types=("steps",),
        )
    )

    sleep_facts = [
        item
        for item in thirty_day.structured_facts
        if item.metadata.get("metric_type") == "sleep_duration"
    ]
    step_facts = [
        item for item in custom.structured_facts if item.metadata.get("metric_type") == "steps"
    ]
    assert sleep_facts
    assert step_facts
    assert step_facts[0].start_date == date(2026, 7, 4)
    assert step_facts[0].end_date == date(2026, 7, 6)
    assert len(step_facts[0].source_record_ids) == 3
    assert set(step_facts[0].source_record_ids).issubset(set(ids["observation_ids"]))


def test_patient_evidence_uses_analytics_summary_instead_of_raw_series(
    database_session: Session,
) -> None:
    user_id = str(uuid4())
    _seed_user(database_session, user_id=user_id, label="SUMMARY_USER")

    result = PatientEvidenceService(database_session).retrieve(
        PatientEvidenceQuery(
            user_id=user_id,
            window_days=7,
            end_at=datetime(2026, 7, 10, 23, tzinfo=UTC),
            metric_types=("steps",),
            include_journals=False,
            include_goals=False,
            include_plans=False,
        )
    )

    step_fact = next(
        item for item in result.structured_facts if item.metadata.get("metric_type") == "steps"
    )
    assert "usable daily observations" in step_fact.fact
    assert "mean=" in step_fact.fact
    assert "slope=" in step_fact.fact
    assert "4000.0, 4100.0" not in step_fact.fact
    assert step_fact.reliability.level.value in {"high", "medium", "low"}


def test_patient_evidence_keyword_retrieves_goals_and_plan_text(database_session: Session) -> None:
    user_id = str(uuid4())
    ids = _seed_user(database_session, user_id=user_id, label="KEYWORD_USER")

    result = PatientEvidenceService(database_session).retrieve(
        PatientEvidenceQuery(
            user_id=user_id,
            window_days=7,
            end_at=datetime(2026, 7, 10, 23, tzinfo=UTC),
            keyword="walk",
            include_journals=False,
        )
    )

    record_ids = {record_id for item in result.items for record_id in item.source_record_ids}
    assert str(ids["goal_id"]) in record_ids
    assert str(ids["plan_id"]) in record_ids
    assert str(ids["action_id"]) in record_ids
