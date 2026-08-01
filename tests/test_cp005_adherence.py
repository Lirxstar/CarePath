from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from backend.analysis_quality import ReliabilityLevel
from backend.domain.models import (
    ActionDifficulty,
    ActionStatus,
    AgeBand,
    Domain,
    FeedbackResponse,
    Goal,
    GoalStatus,
    InterventionPlan,
    Language,
    PlanAction,
    PlanFeedback,
    PlanStatus,
    UserProfile,
)
from backend.personalization.analysis import (
    build_personalization_summary,
    difficulty_signal,
    summarise_adherence,
)
from backend.personalization.models import DifficultyDirection

USER_ID = UUID("20000000-0000-0000-0000-000000000001")
GOAL_ID = UUID("20000000-0000-0000-0000-000000000002")
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _plan(
    number: int,
    status: PlanStatus = PlanStatus.ACTIVE,
    *,
    goal_id: UUID = GOAL_ID,
    start_day: int = 0,
) -> InterventionPlan:
    return InterventionPlan(
        plan_id=UUID(f"20000000-0000-0000-0000-{number:012d}"),
        user_id=USER_ID,
        goal_id=goal_id,
        version=max(1, number),
        start_date=(BASE + timedelta(days=start_day)).date(),
        end_date=(BASE + timedelta(days=start_day + 30)).date(),
        status=status,
        generation_interaction_id=UUID(f"21000000-0000-0000-0000-{number:012d}"),
    )


def _action(
    number: int,
    plan: InterventionPlan,
    *,
    difficulty: ActionDifficulty = ActionDifficulty.HIGH,
    domain: Domain = Domain.SLEEP,
) -> PlanAction:
    return PlanAction(
        action_id=UUID(f"22000000-0000-0000-0000-{number:012d}"),
        plan_id=plan.plan_id,
        domain=domain,
        description="structured adherence test action",
        frequency="daily",
        difficulty=difficulty,
        rationale="deterministic CP-005 test",
        status=ActionStatus.ACCEPTED,
    )


def _feedback(
    number: int,
    action: PlanAction,
    response: FeedbackResponse,
    day: int,
    *,
    ratio: float | None = None,
    feedback_id: UUID | None = None,
) -> PlanFeedback:
    return PlanFeedback(
        feedback_id=feedback_id or UUID(f"23000000-0000-0000-0000-{number:012d}"),
        action_id=action.action_id,
        user_id=USER_ID,
        response=response,
        completion_ratio=ratio,
        created_at=BASE + timedelta(days=day),
    )


def test_repeated_high_difficulty_failure_produces_reduce_signal() -> None:
    plan = _plan(1, PlanStatus.COMPLETED)
    action = _action(1, plan)
    feedback = [
        _feedback(index, action, FeedbackResponse.NOT_COMPLETED, index) for index in range(1, 4)
    ]

    summary = summarise_adherence([action], feedback, [plan])
    signal = difficulty_signal(summary)

    assert summary.completion_rate == 0
    assert summary.not_completed_count == 3
    assert {pattern.pattern_type for pattern in summary.patterns} >= {
        "repeated_non_completion_or_rejection",
        "high_difficulty_low_adherence",
        "consecutive_non_completion_or_rejection",
    }
    assert signal.recommended_difficulty_direction is DifficultyDirection.REDUCE
    assert signal.reason_codes == ("high_difficulty_low_adherence",)
    assert signal.supporting_feedback_ids == summary.source_feedback_ids


def test_stable_high_completion_produces_increase_signal() -> None:
    plan = _plan(2, PlanStatus.ACTIVE)
    action = _action(2, plan, difficulty=ActionDifficulty.MEDIUM)
    feedback = [
        _feedback(index + 10, action, FeedbackResponse.COMPLETED, index) for index in range(3)
    ]

    summary = summarise_adherence([action], feedback, [plan])
    signal = difficulty_signal(summary)

    assert summary.completion_rate == 1
    assert summary.reliability.level is ReliabilityLevel.HIGH
    assert signal.recommended_difficulty_direction is DifficultyDirection.INCREASE


def test_insufficient_feedback_is_conservative() -> None:
    plan = _plan(3)
    action = _action(3, plan)
    feedback = [_feedback(20, action, FeedbackResponse.COMPLETED, 0)]

    summary = summarise_adherence([action], feedback, [plan])
    signal = difficulty_signal(summary)

    assert summary.reliability.level is ReliabilityLevel.LOW
    assert signal.recommended_difficulty_direction is DifficultyDirection.MAINTAIN
    assert signal.reason_codes == ("insufficient_adherence_data",)


def test_partial_without_ratio_is_unresolved_not_guessed() -> None:
    plan = _plan(4)
    action = _action(4, plan, difficulty=ActionDifficulty.LOW)
    feedback = [
        _feedback(30, action, FeedbackResponse.PARTIALLY_COMPLETED, 0, ratio=0.4),
        _feedback(31, action, FeedbackResponse.PARTIALLY_COMPLETED, 1),
        _feedback(32, action, FeedbackResponse.COMPLETED, 2),
    ]

    summary = summarise_adherence([action], feedback, [plan])

    assert summary.partially_completed_count == 2
    assert summary.scored_feedback_count == 2
    assert summary.unresolved_count == 1
    assert summary.completion_rate == 0.7
    assert summary.by_difficulty["low"].total_feedback_count == 3


def test_recent_and_historical_baseline_are_separate() -> None:
    plan = _plan(5)
    action = _action(5, plan, domain=Domain.PHYSICAL_ACTIVITY)
    feedback = [
        _feedback(40, action, FeedbackResponse.COMPLETED, 0),
        _feedback(41, action, FeedbackResponse.COMPLETED, 1),
        _feedback(42, action, FeedbackResponse.NOT_COMPLETED, 10),
    ]

    summary = summarise_adherence(
        [action],
        feedback,
        [plan],
        now=BASE + timedelta(days=10),
        recent_days=3,
    )

    assert summary.historical_baseline.completion_rate == 1
    assert summary.historical_baseline.scored_feedback_count == 2
    assert summary.recent.completion_rate == 0
    assert summary.recent.scored_feedback_count == 1
    assert summary.by_domain["physical_activity"].completion_rate == 2 / 3


def test_conflicting_duplicate_feedback_is_excluded() -> None:
    plan = _plan(6)
    action = _action(6, plan)
    shared_id = UUID("23000000-0000-0000-0000-000000000060")
    feedback = [
        _feedback(60, action, FeedbackResponse.COMPLETED, 0, feedback_id=shared_id),
        _feedback(61, action, FeedbackResponse.NOT_COMPLETED, 0, feedback_id=shared_id),
        _feedback(62, action, FeedbackResponse.COMPLETED, 1),
    ]

    summary = summarise_adherence([action], feedback, [plan])

    assert summary.conflicting_count == 1
    assert summary.scored_feedback_count == 1
    assert summary.completion_rate == 1
    assert "conflicting_feedback_excluded" in summary.warnings
    assert summary.source_feedback_ids == (shared_id, feedback[2].feedback_id)


def test_cancelled_plan_is_excluded_but_superseded_history_is_scored() -> None:
    superseded = _plan(7, PlanStatus.SUPERSEDED)
    cancelled = _plan(8, PlanStatus.CANCELLED)
    historical_action = _action(7, superseded)
    cancelled_action = _action(8, cancelled)
    feedback = [
        _feedback(70, historical_action, FeedbackResponse.COMPLETED, 0),
        _feedback(80, cancelled_action, FeedbackResponse.NOT_COMPLETED, 1),
    ]

    summary = summarise_adherence(
        [historical_action, cancelled_action], feedback, [superseded, cancelled]
    )

    assert summary.total_feedback_count == 1
    assert summary.completed_count == 1
    assert summary.not_completed_count == 0
    assert summary.completion_rate == 1
    assert "draft_or_cancelled_plan_excluded" in summary.warnings
    assert "feedback_for_ineligible_or_unknown_action_excluded" in summary.warnings
    assert set(summary.source_plan_ids) == {superseded.plan_id, cancelled.plan_id}
    assert set(summary.source_goal_ids) == {GOAL_ID}


def test_personalization_summary_selects_active_and_historical_plans() -> None:
    old_plan = _plan(9, PlanStatus.SUPERSEDED, start_day=0)
    active_plan = _plan(10, PlanStatus.ACTIVE, start_day=31)
    cancelled_plan = _plan(11, PlanStatus.CANCELLED, start_day=60)
    action = _action(9, old_plan, difficulty=ActionDifficulty.LOW)
    feedback = [
        _feedback(90, action, FeedbackResponse.COMPLETED, 0),
        _feedback(91, action, FeedbackResponse.COMPLETED, 1),
        _feedback(92, action, FeedbackResponse.COMPLETED, 2),
    ]
    adherence = summarise_adherence([action], feedback, [old_plan, active_plan, cancelled_plan])
    profile = UserProfile(
        user_id=USER_ID,
        age_band=AgeBand.AGE_30_44,
        preferred_language=Language.EN,
        timezone="Asia/Tokyo",
        health_goals=[Domain.SLEEP],
        consent_flags={"synthetic_data": True},
    )
    goal = Goal(
        goal_id=GOAL_ID,
        user_id=USER_ID,
        domain=Domain.SLEEP,
        description="maintain a sustainable sleep routine",
        status=GoalStatus.ACTIVE,
        created_at=BASE,
        target_date=date(2026, 3, 1),
    )

    result = build_personalization_summary(
        profile, [goal], [old_plan, active_plan, cancelled_plan], adherence
    )

    assert result.current_plan_id == active_plan.plan_id
    assert result.previous_plan_ids == (old_plan.plan_id,)
    assert result.activity_constraints == ()
    assert result.source_goal_ids == (GOAL_ID,)
    assert result.difficulty_signal.supporting_plan_ids == adherence.source_plan_ids
