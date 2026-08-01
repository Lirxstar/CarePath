"""Deterministic user-state compression for agent context."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.analysis_quality import ReliabilityLevel
from backend.domain.models import (
    ActionDifficulty,
    ActionStatus,
    Domain,
    FeedbackResponse,
    Goal,
    GoalStatus,
    InterventionPlan,
    MetricType,
    Observation,
    ObservationUnit,
    PlanAction,
    PlanFeedback,
    PlanStatus,
    QualityFlag,
    SourceType,
)
from backend.personalization.analysis import summarise_adherence
from backend.storage.models import (
    GoalTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    PlanFeedbackTable,
    UserProfileTable,
)
from backend.timeseries import compare_periods, compute_trend
from backend.timeseries.config import UNIT_BY_METRIC

_MIN_COVERAGE = 0.5
_SIGNIFICANT_CHANGE = 0.10
_MAX_JOURNALS = 5
_MAX_ACTIONS = 5
_GOAL_METRICS: dict[Domain, tuple[MetricType, ...]] = {
    Domain.SLEEP: (MetricType.SLEEP_DURATION,),
    Domain.PHYSICAL_ACTIVITY: (MetricType.STEPS, MetricType.ACTIVE_MINUTES),
    Domain.STRESS_MOOD: (MetricType.STRESS_SCORE, MetricType.MOOD_SCORE),
    Domain.FALLS_ACTIVITY_SAFETY: (MetricType.ACTIVITY_CONFIDENCE,),
}


class SummaryStatementKind(StrEnum):
    FACT = "fact"
    SUBJECTIVE = "subjective"
    INFERENCE = "inference"


class SummaryStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SummaryStatementKind
    text: str = Field(min_length=1)
    source_record_ids: tuple[str, ...] = ()


class MetricWindowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_type: MetricType
    window_days: int
    start_date: date
    end_date: date
    mean: float | None
    slope_per_day: float | None
    coverage: float = Field(ge=0, le=1)
    missing_rate: float = Field(ge=0, le=1)
    sample_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)
    reliability: ReliabilityLevel
    data_sufficient: bool
    source_record_ids: tuple[str, ...]


class SignificantTrend(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_type: MetricType
    direction: str
    current_mean: float
    baseline_mean: float
    percentage_change: float
    source_record_ids: tuple[str, ...]


class AdherenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    completion_rate: float | None = Field(default=None, ge=0, le=1)
    recent_completion_rate: float | None = Field(default=None, ge=0, le=1)
    scored_feedback_count: int = Field(ge=0)
    total_feedback_count: int = Field(ge=0)
    reliability: ReliabilityLevel
    source_record_ids: tuple[str, ...]


class UserStateSummary(BaseModel):
    """Bounded context consumed by tools/planning instead of raw longitudinal records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    generated_at: datetime
    goals: tuple[str, ...]
    metrics_7d: tuple[MetricWindowSummary, ...]
    metrics_30d: tuple[MetricWindowSummary, ...]
    significant_trends: tuple[SignificantTrend, ...]
    journal_themes: tuple[str, ...]
    recent_actions: tuple[str, ...]
    adherence: AdherenceContext
    preferences: dict[str, object]
    constraints: dict[str, object]
    facts: tuple[SummaryStatement, ...]
    subjective_descriptions: tuple[SummaryStatement, ...]
    inferences: tuple[SummaryStatement, ...]
    data_insufficient: tuple[str, ...]
    source_record_ids: tuple[str, ...]

    def metric(self, metric_type: MetricType, window_days: int) -> MetricWindowSummary | None:
        items = self.metrics_7d if window_days == 7 else self.metrics_30d
        return next((item for item in items if item.metric_type is metric_type), None)


class ContextBuilderService:
    """Build the 7/30-day user state from one user's persisted records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(self, user_id: UUID, *, end_at: datetime | None = None) -> UserStateSummary:
        profile = self.session.get(UserProfileTable, str(user_id))
        if profile is None:
            raise ValueError("patient profile does not exist")
        resolved_end = _as_utc(end_at or datetime.now(UTC))
        observations = self._observations(user_id, resolved_end)
        grouped: dict[MetricType, list[Observation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.metric_type].append(observation)

        metrics_7d = self._metric_windows(grouped, 7, resolved_end.date())
        metrics_30d = self._metric_windows(grouped, 30, resolved_end.date())
        significant = self._significant_trends(grouped, resolved_end.date())
        goals = self._goals(user_id)
        plans, actions, feedback = self._plan_history(user_id)
        adherence_summary = summarise_adherence(
            actions,
            feedback,
            plans,
            now=resolved_end,
            recent_days=7,
        )
        adherence = AdherenceContext(
            completion_rate=adherence_summary.completion_rate,
            recent_completion_rate=adherence_summary.recent.completion_rate,
            scored_feedback_count=adherence_summary.scored_feedback_count,
            total_feedback_count=adherence_summary.total_feedback_count,
            reliability=adherence_summary.reliability.level,
            source_record_ids=_dedupe(
                *(str(item) for item in adherence_summary.source_plan_ids),
                *(str(item) for item in adherence_summary.source_action_ids),
                *(str(item) for item in adherence_summary.source_feedback_ids),
            ),
        )
        journal_rows = self.session.scalars(
            select(JournalEntryTable)
            .where(
                JournalEntryTable.user_id == str(user_id),
                JournalEntryTable.created_at >= resolved_end - timedelta(days=29),
                JournalEntryTable.created_at <= resolved_end,
            )
            .order_by(JournalEntryTable.created_at.desc(), JournalEntryTable.entry_id)
        ).all()
        themes = _journal_themes(list(journal_rows))
        subjective = tuple(
            SummaryStatement(
                kind=SummaryStatementKind.SUBJECTIVE,
                text=row.text,
                source_record_ids=(row.entry_id,),
            )
            for row in journal_rows[:_MAX_JOURNALS]
        )

        active_goals = tuple(
            f"{goal.domain.value}: {goal.description}"
            for goal in goals
            if goal.status is GoalStatus.ACTIVE
        )
        recent_actions = tuple(action.description for action in actions[-_MAX_ACTIONS:])
        facts = self._fact_statements(active_goals, metrics_7d, metrics_30d, adherence)
        inferences = tuple(
            SummaryStatement(
                kind=SummaryStatementKind.INFERENCE,
                text=(
                    f"Behavioural/statistical signal: {item.metric_type.value} "
                    f"{item.direction} versus the previous 7-day window."
                ),
                source_record_ids=item.source_record_ids,
            )
            for item in significant
        )
        insufficient_values = [
            f"{item.metric_type.value}:{item.window_days}d"
            for item in (*metrics_7d, *metrics_30d)
            if not item.data_sufficient
        ]
        available = {(item.metric_type, item.window_days) for item in (*metrics_7d, *metrics_30d)}
        for raw_domain in profile.health_goals:
            try:
                domain = Domain(raw_domain)
            except ValueError:
                continue
            for metric in _GOAL_METRICS[domain]:
                for window_days in (7, 30):
                    if (metric, window_days) not in available:
                        insufficient_values.append(f"{metric.value}:{window_days}d")
        insufficient = _dedupe(*insufficient_values)
        preferences = dict(profile.coaching_preferences or {})
        constraints: dict[str, object] = dict(profile.schedule_constraints or {})
        if profile.activity_constraints:
            constraints["activity_constraints"] = list(profile.activity_constraints)

        source_ids = _dedupe(
            profile.user_id,
            *(str(goal.goal_id) for goal in goals),
            *(
                str(item)
                for metric in (*metrics_7d, *metrics_30d)
                for item in metric.source_record_ids
            ),
            *(row.entry_id for row in journal_rows[:_MAX_JOURNALS]),
            *adherence.source_record_ids,
        )
        return UserStateSummary(
            user_id=user_id,
            generated_at=resolved_end,
            goals=active_goals,
            metrics_7d=metrics_7d,
            metrics_30d=metrics_30d,
            significant_trends=significant,
            journal_themes=themes,
            recent_actions=recent_actions,
            adherence=adherence,
            preferences=preferences,
            constraints=constraints,
            facts=facts,
            subjective_descriptions=subjective,
            inferences=inferences,
            data_insufficient=insufficient,
            source_record_ids=source_ids,
        )

    def _observations(self, user_id: UUID, end_at: datetime) -> list[Observation]:
        rows = self.session.scalars(
            select(ObservationTable)
            .where(
                ObservationTable.user_id == str(user_id),
                ObservationTable.observed_at >= end_at - timedelta(days=59),
                ObservationTable.observed_at <= end_at,
            )
            .order_by(ObservationTable.observed_at, ObservationTable.observation_id)
        ).all()
        return [_observation(row) for row in rows]

    @staticmethod
    def _metric_windows(
        grouped: dict[MetricType, list[Observation]], window_days: int, end_date: date
    ) -> tuple[MetricWindowSummary, ...]:
        output: list[MetricWindowSummary] = []
        for metric in sorted(grouped, key=lambda item: item.value):
            if UNIT_BY_METRIC[metric] is None:
                continue
            trend = compute_trend(
                grouped[metric], days=window_days, end_date=end_date, metric=metric
            )
            sufficient = (
                trend.mean is not None
                and trend.coverage >= _MIN_COVERAGE
                and trend.reliability.level is not ReliabilityLevel.LOW
            )
            output.append(
                MetricWindowSummary(
                    metric_type=metric,
                    window_days=window_days,
                    start_date=trend.start_date,
                    end_date=trend.end_date,
                    mean=trend.mean,
                    slope_per_day=trend.slope_per_day,
                    coverage=trend.coverage,
                    missing_rate=trend.missingness,
                    sample_count=trend.sample_count,
                    expected_count=trend.expected_count,
                    reliability=trend.reliability.level,
                    data_sufficient=sufficient,
                    source_record_ids=tuple(str(item) for item in trend.source_observation_ids),
                )
            )
        return tuple(output)

    @staticmethod
    def _significant_trends(
        grouped: dict[MetricType, list[Observation]], end_date: date
    ) -> tuple[SignificantTrend, ...]:
        output: list[SignificantTrend] = []
        for metric in sorted(grouped, key=lambda item: item.value):
            if UNIT_BY_METRIC[metric] is None:
                continue
            result = compare_periods(
                grouped[metric], end_date=end_date, window_days=7, metric=metric
            )
            if (
                result.percentage_change is None
                or abs(result.percentage_change) < _SIGNIFICANT_CHANGE * 100
                or result.current_mean is None
                or result.baseline_mean is None
                or result.reliability.level is ReliabilityLevel.LOW
            ):
                continue
            direction = "increased" if result.percentage_change > 0 else "decreased"
            output.append(
                SignificantTrend(
                    metric_type=metric,
                    direction=direction,
                    current_mean=result.current_mean,
                    baseline_mean=result.baseline_mean,
                    percentage_change=result.percentage_change,
                    source_record_ids=_dedupe(
                        *(str(item) for item in result.source_observation_ids),
                        *(str(item) for item in result.baseline_source_observation_ids),
                    ),
                )
            )
        return tuple(output)

    def _goals(self, user_id: UUID) -> list[Goal]:
        rows = self.session.scalars(
            select(GoalTable)
            .where(GoalTable.user_id == str(user_id))
            .order_by(GoalTable.created_at, GoalTable.goal_id)
        ).all()
        return [
            Goal(
                goal_id=UUID(row.goal_id),
                user_id=user_id,
                domain=Domain(row.domain),
                description=row.description,
                status=GoalStatus(row.status),
                created_at=_as_utc(row.created_at),
                target_date=row.target_date,
            )
            for row in rows
        ]

    def _plan_history(
        self, user_id: UUID
    ) -> tuple[list[InterventionPlan], list[PlanAction], list[PlanFeedback]]:
        plan_rows = self.session.scalars(
            select(InterventionPlanTable)
            .where(InterventionPlanTable.user_id == str(user_id))
            .order_by(InterventionPlanTable.start_date, InterventionPlanTable.version)
        ).all()
        plans = [_plan(row) for row in plan_rows]
        plan_ids = [row.plan_id for row in plan_rows]
        action_rows = (
            self.session.scalars(
                select(PlanActionTable).where(PlanActionTable.plan_id.in_(plan_ids))
            ).all()
            if plan_ids
            else []
        )
        actions = [_action(row) for row in action_rows]
        action_ids = [row.action_id for row in action_rows]
        feedback_rows = (
            self.session.scalars(
                select(PlanFeedbackTable)
                .where(
                    PlanFeedbackTable.user_id == str(user_id),
                    PlanFeedbackTable.action_id.in_(action_ids),
                )
                .order_by(PlanFeedbackTable.created_at, PlanFeedbackTable.feedback_id)
            ).all()
            if action_ids
            else []
        )
        return plans, actions, [_feedback(row) for row in feedback_rows]

    @staticmethod
    def _fact_statements(
        goals: tuple[str, ...],
        metrics_7d: tuple[MetricWindowSummary, ...],
        metrics_30d: tuple[MetricWindowSummary, ...],
        adherence: AdherenceContext,
    ) -> tuple[SummaryStatement, ...]:
        statements = [
            SummaryStatement(kind=SummaryStatementKind.FACT, text=f"Active goal: {goal}")
            for goal in goals
        ]
        for metric in (*metrics_7d, *metrics_30d):
            mean = "unavailable" if metric.mean is None else f"{metric.mean:.3g}"
            statements.append(
                SummaryStatement(
                    kind=SummaryStatementKind.FACT,
                    text=(
                        f"{metric.metric_type.value} {metric.window_days}-day tool summary: "
                        f"mean={mean}; coverage={metric.coverage:.0%}; "
                        f"missing={metric.missing_rate:.0%}."
                    ),
                    source_record_ids=metric.source_record_ids,
                )
            )
        if adherence.total_feedback_count:
            rate = (
                "unavailable"
                if adherence.completion_rate is None
                else f"{adherence.completion_rate:.0%}"
            )
            statements.append(
                SummaryStatement(
                    kind=SummaryStatementKind.FACT,
                    text=f"Structured plan-feedback completion rate={rate}.",
                    source_record_ids=adherence.source_record_ids,
                )
            )
        return tuple(statements)


def _journal_themes(rows: list[JournalEntryTable]) -> tuple[str, ...]:
    themes: set[str] = set()
    keywords = {
        "sleep": ("sleep", "睡", "眠"),
        "stress": ("stress", "pressure", "压力", "ストレス", "負担"),
        "activity": ("walk", "activity", "move", "活动", "歩", "動"),
        "mood": ("mood", "energy", "情绪", "気分", "体調"),
    }
    for row in rows:
        themes.update(
            tag for tag in (row.user_tags or []) if tag not in {"synthetic", "change_point_window"}
        )
        folded = row.text.casefold()
        for theme, terms in keywords.items():
            if any(term in folded for term in terms):
                themes.add(theme)
    return tuple(sorted(themes))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _observation(row: ObservationTable) -> Observation:
    return Observation(
        observation_id=UUID(row.observation_id),
        user_id=UUID(row.user_id),
        metric_type=MetricType(row.metric_type),
        value_numeric=row.value_numeric,
        value_boolean=row.value_boolean,
        unit=ObservationUnit(row.unit) if row.unit else None,
        observed_at=_as_utc(row.observed_at),
        source_type=SourceType(row.source_type),
        quality_flag=QualityFlag(row.quality_flag),
        confidence=row.confidence,
        metadata=row.metadata_json,
    )


def _plan(row: InterventionPlanTable) -> InterventionPlan:
    return InterventionPlan(
        plan_id=UUID(row.plan_id),
        user_id=UUID(row.user_id),
        goal_id=UUID(row.goal_id),
        version=row.version,
        start_date=row.start_date,
        end_date=row.end_date,
        status=PlanStatus(row.status),
        generation_interaction_id=UUID(row.generation_interaction_id),
        supersedes_plan_id=UUID(row.supersedes_plan_id) if row.supersedes_plan_id else None,
    )


def _action(row: PlanActionTable) -> PlanAction:
    return PlanAction(
        action_id=UUID(row.action_id),
        plan_id=UUID(row.plan_id),
        domain=Domain(row.domain),
        description=row.description,
        frequency=row.frequency,
        difficulty=ActionDifficulty(row.difficulty),
        rationale=row.rationale,
        status=ActionStatus(row.status),
    )


def _feedback(row: PlanFeedbackTable) -> PlanFeedback:
    return PlanFeedback(
        feedback_id=UUID(row.feedback_id),
        action_id=UUID(row.action_id),
        user_id=UUID(row.user_id),
        response=FeedbackResponse(row.response),
        completion_ratio=row.completion_ratio,
        reason_text=row.reason_text,
        created_at=_as_utc(row.created_at),
    )


def _dedupe(*values: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
