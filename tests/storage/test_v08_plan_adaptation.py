from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from backend.domain.models import ActionDifficulty, FeedbackResponse
from backend.personalization.models import DifficultyDirection
from backend.personalization.planner import DailyActionTemplate, InterventionPlanner
from backend.storage.models import GoalTable, InteractionTable, UserProfileTable

USER_ID = UUID("91111111-1111-4111-8111-111111111111")
GOAL_ID = UUID("92222222-2222-4222-8222-222222222222")
INTERACTION_1 = UUID("93333333-3333-4333-8333-333333333333")
INTERACTION_2 = UUID("94444444-4444-4444-8444-444444444444")
START = date(2026, 7, 30)
FEEDBACK_START = datetime(2026, 7, 30, 20, tzinfo=UTC)


def _seed(session: Session) -> None:
    session.add(
        UserProfileTable(
            user_id=str(USER_ID),
            age_band="30-44",
            preferred_language="en",
            timezone="Asia/Tokyo",
            schedule_constraints={"weekday_evening_minutes": 20},
            health_goals=["physical_activity"],
            activity_constraints=None,
            coaching_preferences={"plan_size": "small"},
            consent_flags={"synthetic_data": True},
        )
    )
    session.flush()
    session.add(
        GoalTable(
            goal_id=str(GOAL_ID),
            user_id=str(USER_ID),
            domain="physical_activity",
            description="Build a sustainable movement routine",
            status="active",
            created_at=datetime(2026, 7, 25, 9, tzinfo=UTC),
            target_date=None,
        )
    )
    for interaction_id, started_at in (
        (INTERACTION_1, datetime(2026, 7, 30, 8, tzinfo=UTC)),
        (INTERACTION_2, datetime(2026, 8, 6, 8, tzinfo=UTC)),
    ):
        session.add(
            InteractionTable(
                interaction_id=str(interaction_id),
                user_id=str(USER_ID),
                request_text="Build a realistic activity plan",
                language="en",
                started_at=started_at,
                completed_at=started_at + timedelta(minutes=1),
                risk_level="routine",
                final_status="completed",
                response_json=None,
            )
        )
    session.flush()


def _template(difficulty: ActionDifficulty) -> DailyActionTemplate:
    return DailyActionTemplate(
        domain="physical_activity",
        description="Walk for 30 minutes at a brisk pace",
        easier_description="Walk for 10 minutes at an easy pace",
        alternative_description="Do five minutes of gentle mobility",
        rationale="A structured synthetic action used to test adaptation.",
        difficulty=difficulty,
    )


def test_repeated_high_difficulty_rejection_shrinks_next_plan(
    database_session: Session,
) -> None:
    _seed(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(ActionDifficulty.HIGH),
    )
    planner.persist_plan(first)
    for offset in range(2):
        planner.record_feedback(
            action_id=first.actions[offset].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.REJECTED,
            completion_ratio=0,
            reason_text="The high-difficulty action was not feasible this week.",
            created_at=FEEDBACK_START + timedelta(days=offset),
        )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(ActionDifficulty.HIGH),
    )

    assert second.adaptation.applied is True
    assert second.adaptation.direction is DifficultyDirection.REDUCE
    assert {action.difficulty for action in second.actions} == {ActionDifficulty.MEDIUM}
    assert {action.description for action in second.actions} == {
        "Walk for 10 minutes at an easy pace"
    }
    assert len(second.adaptation.source_feedback_ids) >= 2


def test_stable_high_completion_can_increase_next_plan_difficulty(
    database_session: Session,
) -> None:
    _seed(database_session)
    planner = InterventionPlanner(database_session)
    first = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_1,
        start_date=START,
        template=_template(ActionDifficulty.LOW),
    )
    planner.persist_plan(first)
    for offset in range(3):
        planner.record_feedback(
            action_id=first.actions[offset].action_id,
            user_id=USER_ID,
            response=FeedbackResponse.COMPLETED,
            completion_ratio=1,
            reason_text="Completed comfortably.",
            created_at=FEEDBACK_START + timedelta(days=offset),
        )

    second = planner.build_seven_day_plan(
        user_id=USER_ID,
        goal_id=GOAL_ID,
        generation_interaction_id=INTERACTION_2,
        start_date=START + timedelta(days=7),
        template=_template(ActionDifficulty.LOW),
    )

    assert second.adaptation.applied is True
    assert second.adaptation.direction is DifficultyDirection.INCREASE
    assert {action.difficulty for action in second.actions} == {ActionDifficulty.MEDIUM}
    assert "stable_high_completion" in second.adaptation.reason_codes
    assert len(second.adaptation.source_feedback_ids) == 3
