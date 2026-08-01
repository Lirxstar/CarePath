from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.models import (
    ActionDifficulty,
    ActionStatus,
    Domain,
    FeedbackResponse,
    InterventionPlan,
    PlanAction,
    PlanFeedback,
    PlanStatus,
)
from backend.personalization.analysis import difficulty_signal, summarise_adherence
from backend.personalization.models import DifficultyDirection
from backend.storage.models import (
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    PlanActionTable,
    PlanFeedbackTable,
)

_FAILURE_PATTERN_TYPES = {
    "repeated_non_completion_or_rejection",
    "consecutive_non_completion_or_rejection",
}

_ACTION_STATUS_BY_FEEDBACK: dict[FeedbackResponse, ActionStatus] = {
    FeedbackResponse.ACCEPTED: ActionStatus.ACCEPTED,
    FeedbackResponse.REJECTED: ActionStatus.REJECTED,
    FeedbackResponse.MODIFIED: ActionStatus.MODIFIED,
    FeedbackResponse.COMPLETED: ActionStatus.COMPLETED,
    FeedbackResponse.PARTIALLY_COMPLETED: ActionStatus.PARTIALLY_COMPLETED,
    FeedbackResponse.NOT_COMPLETED: ActionStatus.NOT_COMPLETED,
}


class DailyActionTemplate(BaseModel):
    """Application-provided action seed used to create a seven-day plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: Domain
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    difficulty: ActionDifficulty
    easier_description: str | None = Field(default=None, min_length=1)
    alternative_description: str | None = Field(default=None, min_length=1)


class PlanAdaptation(BaseModel):
    """Traceable adaptation decision derived only from structured feedback history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: DifficultyDirection
    applied: bool
    reason_codes: tuple[str, ...] = ()
    source_action_ids: tuple[UUID, ...] = ()
    source_feedback_ids: tuple[UUID, ...] = ()


class SevenDayPlan(BaseModel):
    """Structured CP-010 output backed by the canonical plan and action models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: InterventionPlan
    actions: tuple[PlanAction, ...]
    adaptation: PlanAdaptation

    @model_validator(mode="after")
    def validate_seven_day_structure(self) -> Self:
        expected_end = self.plan.start_date + timedelta(days=6)
        if self.plan.end_date != expected_end:
            raise ValueError("seven-day plans must span exactly seven calendar days")
        if len(self.actions) != 7:
            raise ValueError("seven-day plans must contain one scheduled action per day")
        if any(action.plan_id != self.plan.plan_id for action in self.actions):
            raise ValueError("all actions must belong to the plan")
        expected_frequencies = {
            f"once on {(self.plan.start_date + timedelta(days=offset)).isoformat()}"
            for offset in range(7)
        }
        if {action.frequency for action in self.actions} != expected_frequencies:
            raise ValueError("actions must cover each day of the seven-day plan exactly once")
        return self


class InterventionPlanner:
    """Persisted, deterministic planner/adaptation service for CP-010."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def build_seven_day_plan(
        self,
        *,
        user_id: UUID,
        goal_id: UUID,
        generation_interaction_id: UUID,
        start_date: date,
        template: DailyActionTemplate,
    ) -> SevenDayPlan:
        """Build a seven-day plan and adapt its action seed from prior structured feedback."""
        self._validate_ownership(user_id, goal_id, generation_interaction_id)
        previous_plans = self._plans_for_goal(user_id, goal_id)
        adaptation = self._adaptation(previous_plans)
        description, difficulty = self._adapt_template(template, adaptation.direction)

        previous = previous_plans[-1] if previous_plans else None
        plan_id = uuid4()
        plan = InterventionPlan(
            plan_id=plan_id,
            user_id=user_id,
            goal_id=goal_id,
            version=(previous.version + 1 if previous is not None else 1),
            start_date=start_date,
            end_date=start_date + timedelta(days=6),
            status=PlanStatus.ACTIVE,
            generation_interaction_id=generation_interaction_id,
            supersedes_plan_id=previous.plan_id if previous is not None else None,
        )
        actions = tuple(
            PlanAction(
                action_id=uuid4(),
                plan_id=plan_id,
                domain=template.domain,
                description=description,
                frequency=f"once on {(start_date + timedelta(days=offset)).isoformat()}",
                difficulty=difficulty,
                rationale=template.rationale,
                status=ActionStatus.PROPOSED,
            )
            for offset in range(7)
        )
        return SevenDayPlan(plan=plan, actions=actions, adaptation=adaptation)

    def persist_plan(self, structured_plan: SevenDayPlan) -> SevenDayPlan:
        """Persist a verified plan and supersede the prior version when applicable."""
        plan = structured_plan.plan
        if self.session.get(InterventionPlanTable, str(plan.plan_id)) is not None:
            raise ValueError("plan already exists")

        if plan.supersedes_plan_id is not None:
            previous = self.session.get(InterventionPlanTable, str(plan.supersedes_plan_id))
            if previous is None:
                raise ValueError("superseded plan does not exist")
            if previous.user_id != str(plan.user_id) or previous.goal_id != str(plan.goal_id):
                raise ValueError("superseded plan does not belong to the same user and goal")
            previous.status = PlanStatus.SUPERSEDED.value

        self.session.add(
            InterventionPlanTable(
                plan_id=str(plan.plan_id),
                user_id=str(plan.user_id),
                goal_id=str(plan.goal_id),
                version=plan.version,
                start_date=plan.start_date,
                end_date=plan.end_date,
                status=plan.status.value,
                generation_interaction_id=str(plan.generation_interaction_id),
                supersedes_plan_id=(
                    str(plan.supersedes_plan_id) if plan.supersedes_plan_id is not None else None
                ),
            )
        )
        self.session.add_all(
            [
                PlanActionTable(
                    action_id=str(action.action_id),
                    plan_id=str(action.plan_id),
                    domain=action.domain.value,
                    description=action.description,
                    frequency=action.frequency,
                    difficulty=action.difficulty.value,
                    rationale=action.rationale,
                    status=action.status.value,
                )
                for action in structured_plan.actions
            ]
        )
        self.session.flush()
        return structured_plan

    def record_feedback(
        self,
        *,
        action_id: UUID,
        user_id: UUID,
        response: FeedbackResponse,
        completion_ratio: float | None = None,
        reason_text: str | None = None,
        created_at: datetime | None = None,
    ) -> PlanFeedback:
        """Persist accepted/rejected/completion feedback and update the action status."""
        action = self.session.get(PlanActionTable, str(action_id))
        if action is None:
            raise ValueError("action does not exist")
        plan = self.session.get(InterventionPlanTable, action.plan_id)
        if plan is None or plan.user_id != str(user_id):
            raise ValueError("action does not belong to the user")

        feedback = PlanFeedback(
            feedback_id=uuid4(),
            action_id=action_id,
            user_id=user_id,
            response=response,
            completion_ratio=completion_ratio,
            reason_text=reason_text,
            created_at=created_at or datetime.now(UTC),
        )
        self.session.add(
            PlanFeedbackTable(
                feedback_id=str(feedback.feedback_id),
                action_id=str(feedback.action_id),
                user_id=str(feedback.user_id),
                response=feedback.response.value,
                completion_ratio=feedback.completion_ratio,
                reason_text=feedback.reason_text,
                created_at=feedback.created_at,
            )
        )
        action.status = _ACTION_STATUS_BY_FEEDBACK[feedback.response].value
        self.session.flush()
        return feedback

    def _validate_ownership(
        self,
        user_id: UUID,
        goal_id: UUID,
        generation_interaction_id: UUID,
    ) -> None:
        goal = self.session.get(GoalTable, str(goal_id))
        if goal is None or goal.user_id != str(user_id):
            raise ValueError("goal does not belong to the user")
        interaction = self.session.get(InteractionTable, str(generation_interaction_id))
        if interaction is None or interaction.user_id != str(user_id):
            raise ValueError("generation interaction does not belong to the user")

    def _plans_for_goal(self, user_id: UUID, goal_id: UUID) -> list[InterventionPlan]:
        rows = self.session.scalars(
            select(InterventionPlanTable)
            .where(
                InterventionPlanTable.user_id == str(user_id),
                InterventionPlanTable.goal_id == str(goal_id),
            )
            .order_by(InterventionPlanTable.version.asc())
        ).all()
        return [self._plan_from_row(row) for row in rows]

    def _adaptation(self, plans: list[InterventionPlan]) -> PlanAdaptation:
        if not plans:
            return PlanAdaptation(
                direction=DifficultyDirection.MAINTAIN,
                applied=False,
                reason_codes=("no_prior_feedback",),
            )

        latest_plan = plans[-1]
        action_rows = self.session.scalars(
            select(PlanActionTable).where(PlanActionTable.plan_id == str(latest_plan.plan_id))
        ).all()
        action_ids = [row.action_id for row in action_rows]
        feedback_rows = (
            self.session.scalars(
                select(PlanFeedbackTable)
                .where(PlanFeedbackTable.action_id.in_(action_ids))
                .order_by(PlanFeedbackTable.created_at.asc(), PlanFeedbackTable.feedback_id.asc())
            ).all()
            if action_ids
            else []
        )
        actions = [self._action_from_row(row) for row in action_rows]
        feedback = [self._feedback_from_row(row) for row in feedback_rows]
        if not feedback:
            return PlanAdaptation(
                direction=DifficultyDirection.MAINTAIN,
                applied=False,
                reason_codes=("no_prior_feedback",),
            )

        summary = summarise_adherence(actions, feedback, [latest_plan])
        signal = difficulty_signal(summary)
        repeated = [
            pattern
            for pattern in summary.patterns
            if pattern.pattern_type in _FAILURE_PATTERN_TYPES and pattern.count >= 2
        ]
        rejected = [item for item in feedback if item.response is FeedbackResponse.REJECTED]
        must_reduce = bool(rejected or repeated)
        direction = (
            DifficultyDirection.REDUCE if must_reduce else signal.recommended_difficulty_direction
        )

        reasons: list[str] = []
        if rejected:
            reasons.append("rejected_action")
        if repeated:
            reasons.append("repeated_failure")
        reasons.extend(signal.reason_codes)

        if must_reduce:
            source_action_ids = tuple(
                dict.fromkeys(
                    [item.action_id for item in rejected]
                    + [action_id for pattern in repeated for action_id in pattern.source_action_ids]
                )
            )
            source_feedback_ids = tuple(
                dict.fromkeys(
                    [item.feedback_id for item in rejected]
                    + [
                        feedback_id
                        for pattern in repeated
                        for feedback_id in pattern.source_feedback_ids
                    ]
                )
            )
        else:
            source_action_ids = signal.supporting_action_ids
            source_feedback_ids = signal.supporting_feedback_ids

        return PlanAdaptation(
            direction=direction,
            applied=direction is not DifficultyDirection.MAINTAIN,
            reason_codes=tuple(dict.fromkeys(reasons)),
            source_action_ids=source_action_ids,
            source_feedback_ids=source_feedback_ids,
        )

    @staticmethod
    def _adapt_template(
        template: DailyActionTemplate,
        direction: DifficultyDirection,
    ) -> tuple[str, ActionDifficulty]:
        if direction is DifficultyDirection.REDUCE:
            if template.difficulty is ActionDifficulty.LOW:
                description = (
                    template.alternative_description
                    or template.easier_description
                    or f"Try a different low-effort version of: {template.description}"
                )
                return description, ActionDifficulty.LOW
            difficulty = (
                ActionDifficulty.MEDIUM
                if template.difficulty is ActionDifficulty.HIGH
                else ActionDifficulty.LOW
            )
            if template.easier_description is not None:
                return template.easier_description, difficulty
            return f"Smaller step: {template.description}", difficulty

        if direction is DifficultyDirection.INCREASE:
            if template.difficulty is ActionDifficulty.LOW:
                return template.description, ActionDifficulty.MEDIUM
            if template.difficulty is ActionDifficulty.MEDIUM:
                return template.description, ActionDifficulty.HIGH
        return template.description, template.difficulty

    @staticmethod
    def _plan_from_row(row: InterventionPlanTable) -> InterventionPlan:
        return InterventionPlan(
            plan_id=UUID(row.plan_id),
            user_id=UUID(row.user_id),
            goal_id=UUID(row.goal_id),
            version=row.version,
            start_date=row.start_date,
            end_date=row.end_date,
            status=PlanStatus(row.status),
            generation_interaction_id=UUID(row.generation_interaction_id),
            supersedes_plan_id=(UUID(row.supersedes_plan_id) if row.supersedes_plan_id else None),
        )

    @staticmethod
    def _action_from_row(row: PlanActionTable) -> PlanAction:
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

    @staticmethod
    def _feedback_from_row(row: PlanFeedbackTable) -> PlanFeedback:
        created_at = row.created_at
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=UTC)
        return PlanFeedback(
            feedback_id=UUID(row.feedback_id),
            action_id=UUID(row.action_id),
            user_id=UUID(row.user_id),
            response=FeedbackResponse(row.response),
            completion_ratio=row.completion_ratio,
            reason_text=row.reason_text,
            created_at=created_at,
        )
