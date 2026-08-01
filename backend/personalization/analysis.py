from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from backend.analysis_quality import ReliabilityLevel, assess_reliability
from backend.domain.models import (
    Goal,
    InterventionPlan,
    PlanAction,
    PlanFeedback,
    PlanStatus,
    UserProfile,
)
from backend.personalization.models import (
    AdherenceBreakdown,
    AdherencePattern,
    AdherenceSummary,
    DifficultyDirection,
    DifficultySignal,
    PersonalizationSummary,
)


def _score(response: str, ratio: float | None) -> float | None:
    if response == "completed":
        return 1.0
    if response in {"partially_completed", "modified"}:
        return ratio
    if response in {"not_completed", "rejected"}:
        return 0.0
    return None


def _breakdown(scores: list[float], total: int) -> AdherenceBreakdown:
    return AdherenceBreakdown(
        completion_rate=sum(scores) / len(scores) if scores else None,
        scored_feedback_count=len(scores),
        total_feedback_count=total,
    )


def _deduplicate_feedback(feedback: list[PlanFeedback]) -> tuple[list[PlanFeedback], set[UUID]]:
    by_id: dict[UUID, PlanFeedback] = {}
    conflicts: set[UUID] = set()
    for item in feedback:
        previous = by_id.get(item.feedback_id)
        if previous is None:
            by_id[item.feedback_id] = item
        elif previous != item:
            conflicts.add(item.feedback_id)
    return sorted(
        by_id.values(), key=lambda item: (item.created_at, str(item.feedback_id))
    ), conflicts


def summarise_adherence(
    actions: list[PlanAction],
    feedback: list[PlanFeedback],
    plans: list[InterventionPlan],
    *,
    now: datetime | None = None,
    recent_days: int = 7,
) -> AdherenceSummary:
    """Summarise structured action feedback without inferring intent from free text."""
    if recent_days < 1:
        raise ValueError("recent_days must be positive")

    warnings: set[str] = set()
    eligible_statuses = {PlanStatus.ACTIVE, PlanStatus.COMPLETED, PlanStatus.SUPERSEDED}
    eligible_plan_ids = {item.plan_id for item in plans if item.status in eligible_statuses}
    if any(item.status not in eligible_statuses for item in plans):
        warnings.add("draft_or_cancelled_plan_excluded")

    action_map = {item.action_id: item for item in actions if item.plan_id in eligible_plan_ids}
    unique_feedback, conflicting_ids = _deduplicate_feedback(feedback)
    eligible_feedback = [item for item in unique_feedback if item.action_id in action_map]
    if len(eligible_feedback) != len(unique_feedback):
        warnings.add("feedback_for_ineligible_or_unknown_action_excluded")

    eligible_conflicting_ids = {
        item.feedback_id for item in eligible_feedback if item.feedback_id in conflicting_ids
    }
    if now is None:
        eligible_times = [
            item.created_at
            for item in eligible_feedback
            if item.feedback_id not in eligible_conflicting_ids
        ]
        if eligible_times:
            now = max(eligible_times)
    cutoff = now - timedelta(days=recent_days) if now is not None else None

    domain_scores: dict[str, list[float]] = defaultdict(list)
    domain_totals: dict[str, int] = defaultdict(int)
    difficulty_scores: dict[str, list[float]] = defaultdict(list)
    difficulty_totals: dict[str, int] = defaultdict(int)
    zero_feedback_by_group: dict[tuple[str, str], list[PlanFeedback]] = defaultdict(list)
    scored_events: list[tuple[PlanFeedback, float]] = []

    counts = {
        "completed": 0,
        "partially_completed": 0,
        "not_completed": 0,
        "rejected": 0,
        "modified": 0,
    }
    recent_scores: list[float] = []
    baseline_scores: list[float] = []
    recent_total = 0
    baseline_total = 0

    for item in eligible_feedback:
        if item.feedback_id in eligible_conflicting_ids:
            continue
        action = action_map[item.action_id]
        if item.response.value in counts:
            counts[item.response.value] += 1

        if cutoff is not None and item.created_at >= cutoff:
            recent_total += 1
        else:
            baseline_total += 1

        domain_totals[action.domain.value] += 1
        difficulty_totals[action.difficulty.value] += 1
        score = _score(item.response.value, item.completion_ratio)
        if score is None:
            continue

        scored_events.append((item, score))
        domain_scores[action.domain.value].append(score)
        difficulty_scores[action.difficulty.value].append(score)
        if cutoff is not None and item.created_at >= cutoff:
            recent_scores.append(score)
        else:
            baseline_scores.append(score)
        if score == 0:
            zero_feedback_by_group[(action.domain.value, action.difficulty.value)].append(item)

    patterns: list[AdherencePattern] = []
    for (domain, difficulty), items in sorted(zero_feedback_by_group.items()):
        if len(items) < 2:
            continue
        patterns.append(
            AdherencePattern(
                pattern_type="repeated_non_completion_or_rejection",
                count=len(items),
                domain=domain,
                difficulty=difficulty,
                source_action_ids=tuple(dict.fromkeys(item.action_id for item in items)),
                source_feedback_ids=tuple(item.feedback_id for item in items),
            )
        )

    high_scores = difficulty_scores.get("high", [])
    if len(high_scores) >= 2 and sum(high_scores) / len(high_scores) < 0.5:
        high_events = [
            item
            for item, score in scored_events
            if action_map[item.action_id].difficulty.value == "high" and score < 0.5
        ]
        patterns.append(
            AdherencePattern(
                pattern_type="high_difficulty_low_adherence",
                count=len(high_events),
                difficulty="high",
                source_action_ids=tuple(dict.fromkeys(item.action_id for item in high_events)),
                source_feedback_ids=tuple(item.feedback_id for item in high_events),
            )
        )

    streak: list[PlanFeedback] = []
    longest: list[PlanFeedback] = []
    for item, score in scored_events:
        if score == 0:
            streak.append(item)
            if len(streak) > len(longest):
                longest = list(streak)
        else:
            streak.clear()
    if len(longest) >= 2:
        patterns.append(
            AdherencePattern(
                pattern_type="consecutive_non_completion_or_rejection",
                count=len(longest),
                source_action_ids=tuple(dict.fromkeys(item.action_id for item in longest)),
                source_feedback_ids=tuple(item.feedback_id for item in longest),
            )
        )

    for domain, values in sorted(domain_scores.items()):
        if len(values) >= 3 and sum(values) / len(values) >= 0.8:
            supporting = [
                item
                for item, score in scored_events
                if action_map[item.action_id].domain.value == domain and score >= 0.8
            ]
            patterns.append(
                AdherencePattern(
                    pattern_type="high_adherence_domain",
                    count=len(supporting),
                    domain=domain,
                    source_action_ids=tuple(dict.fromkeys(item.action_id for item in supporting)),
                    source_feedback_ids=tuple(item.feedback_id for item in supporting),
                )
            )

    if eligible_conflicting_ids:
        warnings.add("conflicting_feedback_excluded")
    if not eligible_feedback:
        warnings.add("no_eligible_feedback")

    total_feedback = len(eligible_feedback)
    scored_count = len(scored_events)
    reliability = assess_reliability(
        expected_count=total_feedback,
        valid_count=scored_count,
        conflicting_count=len(eligible_conflicting_ids),
    )
    eligible_actions = list(action_map.values())

    return AdherenceSummary(
        completion_rate=(
            sum(score for _, score in scored_events) / scored_count if scored_count else None
        ),
        completed_count=counts["completed"],
        partially_completed_count=counts["partially_completed"],
        not_completed_count=counts["not_completed"],
        rejected_count=counts["rejected"],
        modified_count=counts["modified"],
        accepted_count=sum(1 for item in eligible_actions if item.status.value == "accepted"),
        unresolved_count=max(0, total_feedback - scored_count - len(eligible_conflicting_ids)),
        conflicting_count=len(eligible_conflicting_ids),
        scored_feedback_count=scored_count,
        total_feedback_count=total_feedback,
        by_domain={
            key: _breakdown(domain_scores.get(key, []), total)
            for key, total in sorted(domain_totals.items())
        },
        by_difficulty={
            key: _breakdown(difficulty_scores.get(key, []), total)
            for key, total in sorted(difficulty_totals.items())
        },
        recent=_breakdown(recent_scores, recent_total),
        historical_baseline=_breakdown(baseline_scores, baseline_total),
        patterns=tuple(patterns),
        reliability=reliability,
        warnings=tuple(sorted(warnings)),
        source_goal_ids=tuple(dict.fromkeys(item.goal_id for item in plans)),
        source_plan_ids=tuple(dict.fromkeys(item.plan_id for item in plans)),
        source_action_ids=tuple(dict.fromkeys(item.action_id for item in actions)),
        source_feedback_ids=tuple(item.feedback_id for item in unique_feedback),
    )


def difficulty_signal(summary: AdherenceSummary) -> DifficultySignal:
    high = summary.by_difficulty.get("high")
    repeated_high_failure = any(
        pattern.pattern_type
        in {"high_difficulty_low_adherence", "repeated_non_completion_or_rejection"}
        and pattern.difficulty == "high"
        for pattern in summary.patterns
    )

    if summary.reliability.level is ReliabilityLevel.LOW:
        direction = DifficultyDirection.MAINTAIN
        reasons = ("insufficient_adherence_data",)
    elif repeated_high_failure or (
        high is not None
        and high.scored_feedback_count >= 2
        and high.completion_rate is not None
        and high.completion_rate < 0.5
    ):
        direction = DifficultyDirection.REDUCE
        reasons = ("high_difficulty_low_adherence",)
    elif (
        summary.completion_rate is not None
        and summary.completion_rate >= 0.9
        and summary.scored_feedback_count >= 3
    ):
        direction = DifficultyDirection.INCREASE
        reasons = ("stable_high_completion",)
    else:
        direction = DifficultyDirection.MAINTAIN
        reasons = ("mixed_adherence",)

    return DifficultySignal(
        recommended_difficulty_direction=direction,
        reason_codes=reasons,
        reliability=summary.reliability,
        supporting_plan_ids=summary.source_plan_ids,
        supporting_action_ids=summary.source_action_ids,
        supporting_feedback_ids=summary.source_feedback_ids,
    )


def build_personalization_summary(
    profile: UserProfile,
    goals: list[Goal],
    plans: list[InterventionPlan],
    adherence: AdherenceSummary,
) -> PersonalizationSummary:
    active_plans = [item for item in plans if item.status is PlanStatus.ACTIVE]
    current = (
        max(active_plans, key=lambda item: (item.start_date, item.version))
        if active_plans
        else None
    )
    previous = [
        item
        for item in plans
        if item.status in {PlanStatus.COMPLETED, PlanStatus.SUPERSEDED}
        and (current is None or item.plan_id != current.plan_id)
    ]
    signal = difficulty_signal(adherence)

    return PersonalizationSummary(
        behavioural_goals=tuple(item.value for item in profile.health_goals),
        schedule_constraints=profile.schedule_constraints,
        activity_constraints=tuple(profile.activity_constraints or ()),
        coaching_preferences=profile.coaching_preferences,
        historical_adherence=adherence.historical_baseline.completion_rate,
        recent_adherence=adherence.recent.completion_rate,
        current_plan_id=current.plan_id if current is not None else None,
        previous_plan_ids=tuple(
            item.plan_id
            for item in sorted(previous, key=lambda item: (item.start_date, item.version))
        ),
        adherence_patterns=adherence.patterns,
        difficulty_signal=signal,
        source_goal_ids=tuple(dict.fromkeys(item.goal_id for item in goals)),
        source_plan_ids=adherence.source_plan_ids,
        source_action_ids=adherence.source_action_ids,
        source_feedback_ids=adherence.source_feedback_ids,
    )
