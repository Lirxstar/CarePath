from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.domain.models import (
    ActionFeedback,
    AuditEvent,
    CarePlan,
    Goal,
    Interaction,
    InterventionPlan,
    JournalEntry,
    KnowledgeChunk,
    KnowledgeSource,
    Observation,
    PlanAction,
    PlanFeedback,
    UserProfile,
)
from backend.domain.persistence import (
    AuditEventRecord,
    GoalRecord,
    InteractionRecord,
    InterventionPlanRecord,
    JournalEntryRecord,
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
    ObservationRecord,
    PlanActionRecord,
    PlanFeedbackRecord,
    UserProfileRecord,
)

USER_ID = uuid4()
BASE_OBSERVATION = {
    "observation_id": uuid4(),
    "user_id": USER_ID,
    "observed_at": "2026-07-27T09:00:00+09:00",
    "source_type": "csv",
}


def test_user_profile_and_observation_contracts() -> None:
    profile = UserProfile(
        user_id=USER_ID,
        age_band="30-44",
        preferred_language="en",
        timezone="Asia/Tokyo",
        health_goals=["sleep"],
        consent_flags={"observations": True},
    )
    observation = Observation(
        **BASE_OBSERVATION,
        metric_type="steps",
        value_numeric=5000,
        unit="steps",
        confidence=0.9,
    )

    assert profile.timezone == "Asia/Tokyo"
    assert observation.observed_at == datetime(2026, 7, 27, 0, 0, tzinfo=UTC)


def test_invalid_units_metrics_missing_ids_and_value_shapes() -> None:
    with pytest.raises(ValidationError):
        Observation(**BASE_OBSERVATION, metric_type="steps", value_numeric=1, unit="hours")
    with pytest.raises(ValidationError):
        Observation(**BASE_OBSERVATION, metric_type="unknown", value_numeric=1, unit="steps")
    with pytest.raises(ValidationError):
        Observation(
            **BASE_OBSERVATION,
            metric_type="steps",
            value_numeric=1,
            unit="steps",
            quality_flag="missing",
        )
    with pytest.raises(ValidationError):
        Observation(**BASE_OBSERVATION, metric_type="steps", value_boolean=True, unit="steps")

    malformed = BASE_OBSERVATION | {"observation_id": "not-a-uuid"}
    with pytest.raises(ValidationError):
        Observation(**malformed, metric_type="steps", value_numeric=1, unit="steps")

    missing = Observation(
        **BASE_OBSERVATION,
        metric_type="steps",
        unit="steps",
        quality_flag="missing",
    )
    assert missing.value_numeric is None


def test_entity_and_persistence_contracts() -> None:
    goal = Goal(
        goal_id=uuid4(),
        user_id=USER_ID,
        domain="sleep",
        description="Sleep",
        status="active",
        created_at="2026-07-27T00:00:00Z",
    )
    plan = InterventionPlan(
        plan_id=uuid4(),
        user_id=USER_ID,
        goal_id=goal.goal_id,
        version=1,
        start_date="2026-07-27",
        end_date="2026-07-28",
        status="active",
        generation_interaction_id=uuid4(),
    )
    action = PlanAction(
        action_id=uuid4(),
        plan_id=plan.plan_id,
        domain="sleep",
        description="Sleep",
        frequency="daily",
        difficulty="low",
        rationale="routine",
        status="accepted",
    )
    feedback = PlanFeedback(
        feedback_id=uuid4(),
        action_id=action.action_id,
        user_id=USER_ID,
        response="completed",
        completion_ratio=1,
        created_at="2026-07-27T00:00:00Z",
    )
    journal = JournalEntry(
        entry_id=uuid4(),
        user_id=USER_ID,
        created_at="2026-07-27T00:00:00Z",
        text="note",
        language="en",
    )
    source = KnowledgeSource(
        source_id="CDC_SLEEP",
        title="About Sleep",
        organisation="CDC",
        url="https://example.org/sleep",
        retrieved_at="2026-07-27",
        trust_tier="T2_GUIDELINE",
        licence_note="public domain",
    )
    chunk = KnowledgeChunk(
        chunk_id="CDC_SLEEP-01",
        source_id=source.source_id,
        content="Adults need regular sleep routines.",
        embedding_model="test-embedding",
        content_hash="a" * 64,
    )
    interaction = Interaction(
        interaction_id=uuid4(),
        user_id=USER_ID,
        request_text="Help me plan my sleep routine",
        language="en",
        started_at="2026-07-27T00:00:00Z",
        completed_at="2026-07-27T00:00:01Z",
        risk_level="routine",
        final_status="completed",
    )
    audit = AuditEvent(
        audit_event_id=uuid4(),
        interaction_id=interaction.interaction_id,
        sequence_number=1,
        event_type="verification",
        component="verifier",
        input_refs={},
        output_summary={},
        created_at="2026-07-27T00:00:01Z",
    )

    records = [
        UserProfileRecord,
        ObservationRecord,
        JournalEntryRecord,
        GoalRecord,
        InterventionPlanRecord,
        PlanActionRecord,
        PlanFeedbackRecord,
        KnowledgeSourceRecord,
        KnowledgeChunkRecord,
        InteractionRecord,
        AuditEventRecord,
    ]
    assert all(record.model_fields for record in records)
    assert (goal.description, feedback.completion_ratio, journal.text) == ("Sleep", 1, "note")
    assert (chunk.source_id, audit.sequence_number) == ("CDC_SLEEP", 1)
    assert CarePlan is InterventionPlan
    assert ActionFeedback is PlanFeedback


def test_interaction_completion_validation() -> None:
    common = {
        "interaction_id": uuid4(),
        "user_id": USER_ID,
        "request_text": "hello",
        "language": "en",
        "started_at": "2026-07-27T00:00:00Z",
        "risk_level": "routine",
    }
    with pytest.raises(ValidationError):
        Interaction(**common, final_status="completed")
    with pytest.raises(ValidationError):
        Interaction(
            **common,
            completed_at="2026-07-27T00:00:01Z",
            final_status="in_progress",
        )


def test_example_observation_json_is_valid() -> None:
    example = Path(__file__).parents[1] / "docs" / "examples" / "observation.json"
    Observation.model_validate_json(example.read_text(encoding="utf-8"))
