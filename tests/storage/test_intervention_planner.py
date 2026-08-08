from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.models import ActionDifficulty, FeedbackResponse
from backend.personalization.models import DifficultyDirection
from backend.personalization.planner import (
    DailyActionTemplate,
    FeedbackSubmissionConflictError,
    InterventionPlanner,
    PlanFeedbackWindowError,
)
from backend.storage.models import (
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    PlanActionTable,
    PlanFeedbackTable,
    UserProfileTable,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
GOAL_ID = UUID("22222222-2222-4222-8222-222222222222")
INTERACTION_1 = UUID("33333333-3333-4333-8333-333333333333")
INTERACTION_2 = UUID("44444444-4444-4444-8444-444444444444")
START = date(2026, 7, 1)


def _seed_user_goal_and_interactions(session: Session) -> None:
    session.add(
        UserProfileTable(
            user_id=str(USER_ID),
            age_band="30-44",
            preferred_language="en",
            timezone="Asia/Tokyo",
            schedule_constraints=None,
            health_goals=["physical_activity"],
            activity_constraints=None,
            coaching_preferences=None,
            consent_flags={"synthetic_data": True},
        )
    )
    session.flush()
    session.add(
        GoalTable(
            goal_id=str(GOAL_ID),
            user_id=str(USER_ID),
            domain="physical_activity",
            description="Build a sustainable activity routine",
            status="active",
            created_at=datetime(2026, 6, 25, 9, tzinfo=UTC),
            target_date=None,
        )
    )
    for interaction_id, started_at in (
        (INTERACTION_1, datetime(2026, 7, 1, 8, tzinfo=UTC)),
        (INTERACTION_2, datetime(2026, 7, 8, 8, tzinfo=UTC)),
    ):
        session.add(
            InteractionTable(
                interaction_id=str(interaction_id),
                user_id=str(USER_ID),
                request_text="Help me make an activity plan",
                language="en",
                started_at=started_at,
                completed_at=started_at + timedelta(minutes=1),
                risk_level="routine",
                final_status="completed",
                response_json=None,
            )
        )
    session.flush()


def _template(difficulty: ActionDifficulty = ActionDifficulty.HIGH) -> DailyActionTemplate:
    return DailyActionTemplate(
        domain="physical_activity",
        description="Walk for 30 minutes at a brisk pace",
        easier_description="Walk for 10 minutes at an easy pace",
        alternative_description="Do five minutes of gentle mobility",
        rationale="Use a concrete, repeatable activity action that can be reviewed after one week.",
        difficulty=difficulty,
    )


def test_structured_plan_spans_exactly_seven_days(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)

    result = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )

    assert result.plan.start_date == START
    assert result.plan.end_date == START + timedelta(days=6)
    assert result.plan.version == 1
    assert len(result.actions) == 7
    assert [action.frequency for action in result.actions] == [
        f"once on {(START + timedelta(days=offset)).isoformat()}" for offset in range(7)
    ]
    assert result.adaptation.applied is False
    assert result.adaptation.reason_codes == ("no_prior_feedback",)


def test_plan_and_action_feedback_are_persisted(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    structured = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(structured)

    planner.record_feedback(
        action_id=structured.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.ACCEPTED,
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
    )
    planner.record_feedback(
        action_id=structured.actions[1].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.REJECTED,
        reason_text="The action was too demanding today.",
        created_at=datetime(2026, 7, 2, 20, tzinfo=UTC),
    )
    planner.record_feedback(
        action_id=structured.actions[2].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.NOT_COMPLETED,
        completion_ratio=0.0,
        created_at=datetime(2026, 7, 3, 20, tzinfo=UTC),
    )

    plan_rows = database_session.scalars(select(InterventionPlanTable)).all()
    action_rows = database_session.scalars(
        select(PlanActionTable).order_by(PlanActionTable.frequency.asc())
    ).all()
    feedback_rows = database_session.scalars(
        select(PlanFeedbackTable).order_by(PlanFeedbackTable.created_at.asc())
    ).all()

    assert len(plan_rows) == 1
    assert len(action_rows) == 7
    assert [row.status for row in action_rows[:3]] == ["accepted", "rejected", "not_completed"]
    assert [row.response for row in feedback_rows] == ["accepted", "rejected", "not_completed"]
    assert all(row.submission_key for row in feedback_rows)


def test_identical_feedback_submission_is_idempotent(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    structured = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(structured)
    created_at = datetime(2026, 7, 1, 20, tzinfo=UTC)

    first = planner.record_feedback(
        action_id=structured.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.ACCEPTED,
        created_at=created_at,
        submission_key="same-feedback-request",
    )
    replay = planner.record_feedback(
        action_id=structured.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.ACCEPTED,
        created_at=created_at + timedelta(minutes=1),
        submission_key="same-feedback-request",
    )

    rows = database_session.scalars(select(PlanFeedbackTable)).all()
    assert replay.feedback_id == first.feedback_id
    assert len(rows) == 1
    assert rows[0].submission_key == "same-feedback-request"


def test_submission_key_cannot_be_reused_for_different_feedback(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    structured = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(structured)
    planner.record_feedback(
        action_id=structured.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.ACCEPTED,
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
        submission_key="conflicting-feedback-request",
    )

    with pytest.raises(FeedbackSubmissionConflictError):
        planner.record_feedback(
            action_id=structured.actions[0].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.REJECTED,
            completion_ratio=0,
            created_at=datetime(2026, 7, 1, 21, tzinfo=UTC),
            submission_key="conflicting-feedback-request",
        )


def test_feedback_is_rejected_outside_active_plan_window(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(first)

    with pytest.raises(PlanFeedbackWindowError) as expired:
        planner.record_feedback(
            action_id=first.actions[0].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.ACCEPTED,
            created_at=datetime(2026, 7, 8, 12, tzinfo=UTC),
        )
    assert expired.value.code == "plan_expired"

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(),
    )
    planner.persist_plan(second)
    with pytest.raises(PlanFeedbackWindowError) as superseded:
        planner.record_feedback(
            action_id=first.actions[1].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.ACCEPTED,
            created_at=datetime(2026, 7, 2, 12, tzinfo=UTC),
        )
    assert superseded.value.code == "plan_not_active"


def test_single_accepted_action_explicitly_maintains_next_plan(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(ActionDifficulty.MEDIUM),
    )
    planner.persist_plan(first)
    accepted = planner.record_feedback(
        action_id=first.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.ACCEPTED,
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
    )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(ActionDifficulty.MEDIUM),
    )

    assert second.adaptation.direction is DifficultyDirection.MAINTAIN
    assert second.adaptation.applied is False
    assert "accepted_current_difficulty" in second.adaptation.reason_codes
    assert second.adaptation.source_action_ids == (first.actions[0].action_id,)
    assert second.adaptation.source_feedback_ids == (accepted.feedback_id,)
    assert {action.difficulty for action in second.actions} == {ActionDifficulty.MEDIUM}


def test_single_rejected_action_changes_next_plan(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(first)
    rejected = planner.record_feedback(
        action_id=first.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.REJECTED,
        reason_text="This is more than I can manage this week.",
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
    )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(),
    )

    assert second.adaptation.direction is DifficultyDirection.REDUCE
    assert "rejected_action" in second.adaptation.reason_codes
    assert second.adaptation.source_action_ids == (first.actions[0].action_id,)
    assert second.adaptation.source_feedback_ids == (rejected.feedback_id,)
    assert {action.difficulty for action in second.actions} == {ActionDifficulty.MEDIUM}
    assert {action.description for action in second.actions} == {
        "Walk for 10 minutes at an easy pace"
    }


def test_rejected_low_difficulty_action_uses_different_alternative(
    database_session: Session,
) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(ActionDifficulty.LOW),
    )
    planner.persist_plan(first)
    planner.record_feedback(
        action_id=first.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.REJECTED,
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
    )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(ActionDifficulty.LOW),
    )

    assert {action.difficulty for action in second.actions} == {ActionDifficulty.LOW}
    assert {action.description for action in second.actions} == {
        "Do five minutes of gentle mobility"
    }


def test_repeated_failure_reduces_next_action(database_session: Session) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(first)

    for offset in range(2):
        planner.record_feedback(
            action_id=first.actions[offset].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.NOT_COMPLETED,
            completion_ratio=0.0,
            created_at=datetime(2026, 7, 1 + offset, 20, tzinfo=UTC),
        )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(),
    )

    assert second.plan.version == 2
    assert second.plan.supersedes_plan_id == first.plan.plan_id
    assert second.adaptation.direction is DifficultyDirection.REDUCE
    assert second.adaptation.applied is True
    assert "repeated_failure" in second.adaptation.reason_codes
    assert len(second.adaptation.source_action_ids) == 2
    assert len(second.adaptation.source_feedback_ids) == 2
    assert {action.difficulty for action in second.actions} == {ActionDifficulty.MEDIUM}
    assert {action.description for action in second.actions} == {
        "Walk for 10 minutes at an easy pace"
    }


def test_automated_feedback_adaptation_scenario_persists_new_version(
    database_session: Session,
) -> None:
    _seed_user_goal_and_interactions(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(),
    )
    planner.persist_plan(first)
    planner.record_feedback(
        action_id=first.actions[0].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.REJECTED,
        created_at=datetime(2026, 7, 1, 20, tzinfo=UTC),
    )
    planner.record_feedback(
        action_id=first.actions[1].action_id,
        user_id=USER_ID,
        response=FeedbackResponse.NOT_COMPLETED,
        completion_ratio=0.0,
        created_at=datetime(2026, 7, 2, 20, tzinfo=UTC),
    )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(),
    )
    planner.persist_plan(second)

    prior_row = database_session.get(InterventionPlanTable, str(first.plan.plan_id))
    next_row = database_session.get(InterventionPlanTable, str(second.plan.plan_id))
    next_actions = database_session.scalars(
        select(PlanActionTable).where(PlanActionTable.plan_id == str(second.plan.plan_id))
    ).all()

    assert prior_row is not None and prior_row.status == "superseded"
    assert next_row is not None and next_row.version == 2
    assert next_row.supersedes_plan_id == str(first.plan.plan_id)
    assert len(next_actions) == 7
    assert {row.difficulty for row in next_actions} == {"medium"}
    assert {row.description for row in next_actions} == {"Walk for 10 minutes at an easy pace"}
