from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain import (
    Goal,
    InterventionPlan,
    JournalEntry,
    Observation,
    PlanAction,
    UserProfile,
)
from backend.domain.models import (
    ActionDifficulty,
    ActionStatus,
    AgeBand,
    Domain,
    GoalStatus,
    Language,
    MetricType,
    ObservationUnit,
    PlanStatus,
    QualityFlag,
    SourceType,
)
from backend.storage.models import (
    GoalTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    UserProfileTable,
)

from .access import ensure_user_access
from .errors import CarePathError
from .session_scope import get_request_session

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_request_session)]
MAX_OBSERVATION_BATCH = 500
MAX_OBSERVATION_PAGE = 100
MAX_PLAN_HISTORY_PAGE = 100
MAX_OBSERVATION_RANGE = timedelta(days=366)


class ObservationBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[Observation] = Field(min_length=1, max_length=MAX_OBSERVATION_BATCH)


class ObservationBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inserted_count: int
    observation_ids: list[UUID]


class ObservationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Observation]
    limit: int
    offset: int
    returned_count: int


class PlanHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: InterventionPlan
    actions: list[PlanAction]


class PlanHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanHistoryItem]
    limit: int
    offset: int
    returned_count: int


def _profile_from_row(row: UserProfileTable) -> UserProfile:
    return UserProfile(
        user_id=UUID(row.user_id),
        age_band=AgeBand(row.age_band),
        preferred_language=Language(row.preferred_language),
        timezone=row.timezone,
        schedule_constraints=row.schedule_constraints,
        health_goals=[Domain(item) for item in row.health_goals],
        activity_constraints=row.activity_constraints,
        coaching_preferences=row.coaching_preferences,
        consent_flags=row.consent_flags,
    )


def _observation_from_row(row: ObservationTable) -> Observation:
    observed_at = row.observed_at
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    else:
        observed_at = observed_at.astimezone(UTC)
    return Observation(
        observation_id=UUID(row.observation_id),
        user_id=UUID(row.user_id),
        metric_type=MetricType(row.metric_type),
        value_numeric=row.value_numeric,
        value_boolean=row.value_boolean,
        unit=ObservationUnit(row.unit) if row.unit is not None else None,
        observed_at=observed_at,
        source_type=SourceType(row.source_type),
        quality_flag=QualityFlag(row.quality_flag),
        confidence=row.confidence,
        metadata=row.metadata_json,
    )


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
        supersedes_plan_id=UUID(row.supersedes_plan_id) if row.supersedes_plan_id else None,
    )


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


def _require_profile(session: Session, user_id: UUID) -> UserProfileTable:
    row = session.get(UserProfileTable, str(user_id))
    if row is None:
        raise CarePathError(
            "profile_not_found",
            "The requested user profile does not exist",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return row


def _validated_query_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CarePathError(
            "timezone_required",
            "Observation range timestamps must include a timezone",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    return value.astimezone(UTC)


@router.get(
    "/profiles/{user_id}",
    response_model=UserProfile,
    summary="Read a CarePath user profile",
)
def read_profile(request: Request, user_id: UUID, session: SessionDependency) -> UserProfile:
    ensure_user_access(request, session, user_id)
    return _profile_from_row(_require_profile(session, user_id))


@router.post(
    "/observations/batch",
    response_model=ObservationBatchResponse,
    status_code=HTTPStatus.CREATED,
    summary="Write a validated batch of canonical observations atomically",
)
def write_observations_batch(
    request: Request,
    payload: ObservationBatchRequest,
    session: SessionDependency,
) -> ObservationBatchResponse:
    ids = [str(item.observation_id) for item in payload.observations]
    if len(ids) != len(set(ids)):
        raise CarePathError(
            "duplicate_observation_id",
            "The observation batch contains duplicate observation IDs",
            status_code=HTTPStatus.CONFLICT,
        )

    for user_id in {item.user_id for item in payload.observations}:
        ensure_user_access(request, session, user_id)
        _require_profile(session, user_id)

    existing_ids = set(
        session.scalars(
            select(ObservationTable.observation_id).where(ObservationTable.observation_id.in_(ids))
        ).all()
    )
    if existing_ids:
        raise CarePathError(
            "observation_exists",
            "At least one observation ID already exists",
            status_code=HTTPStatus.CONFLICT,
        )

    session.add_all(
        [
            ObservationTable(
                observation_id=str(item.observation_id),
                user_id=str(item.user_id),
                metric_type=item.metric_type.value,
                value_numeric=item.value_numeric,
                value_boolean=item.value_boolean,
                unit=item.unit.value if item.unit is not None else None,
                observed_at=item.observed_at,
                source_type=item.source_type.value,
                quality_flag=item.quality_flag.value,
                confidence=item.confidence,
                metadata_json=item.metadata,
            )
            for item in payload.observations
        ]
    )
    session.commit()
    return ObservationBatchResponse(
        inserted_count=len(payload.observations),
        observation_ids=[item.observation_id for item in payload.observations],
    )


@router.get(
    "/observations",
    response_model=ObservationPage,
    summary="Read observations in a bounded date range",
)
def read_observations(
    request: Request,
    user_id: UUID,
    start_at: datetime,
    end_at: datetime,
    session: SessionDependency,
    metric_type: MetricType | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_OBSERVATION_PAGE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ObservationPage:
    ensure_user_access(request, session, user_id)
    _require_profile(session, user_id)
    start = _validated_query_time(start_at)
    end = _validated_query_time(end_at)
    if end < start:
        raise CarePathError(
            "invalid_date_range",
            "end_at must not be before start_at",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if end - start > MAX_OBSERVATION_RANGE:
        raise CarePathError(
            "date_range_too_large",
            "Observation date ranges are limited to 366 days",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    statement = select(ObservationTable).where(
        ObservationTable.user_id == str(user_id),
        ObservationTable.observed_at >= start,
        ObservationTable.observed_at <= end,
    )
    if metric_type is not None:
        statement = statement.where(ObservationTable.metric_type == metric_type.value)
    rows = session.scalars(
        statement.order_by(
            ObservationTable.observed_at.asc(),
            ObservationTable.observation_id.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()
    items = [_observation_from_row(row) for row in rows]
    return ObservationPage(
        items=items,
        limit=limit,
        offset=offset,
        returned_count=len(items),
    )


@router.post(
    "/journals",
    response_model=JournalEntry,
    status_code=HTTPStatus.CREATED,
    summary="Write one canonical journal entry",
)
def write_journal(
    request: Request,
    entry: JournalEntry,
    session: SessionDependency,
) -> JournalEntry:
    ensure_user_access(request, session, entry.user_id)
    _require_profile(session, entry.user_id)
    if session.get(JournalEntryTable, str(entry.entry_id)) is not None:
        raise CarePathError(
            "journal_entry_exists",
            "A journal entry with this entry_id already exists",
            status_code=HTTPStatus.CONFLICT,
        )
    session.add(
        JournalEntryTable(
            entry_id=str(entry.entry_id),
            user_id=str(entry.user_id),
            created_at=entry.created_at,
            text=entry.text,
            language=entry.language.value,
            user_tags=entry.user_tags,
        )
    )
    session.commit()
    return entry


@router.post(
    "/goals",
    response_model=Goal,
    status_code=HTTPStatus.CREATED,
    summary="Create one canonical behavioural goal",
)
def create_goal(request: Request, goal: Goal, session: SessionDependency) -> Goal:
    ensure_user_access(request, session, goal.user_id)
    _require_profile(session, goal.user_id)
    if session.get(GoalTable, str(goal.goal_id)) is not None:
        raise CarePathError(
            "goal_exists",
            "A goal with this goal_id already exists",
            status_code=HTTPStatus.CONFLICT,
        )
    session.add(
        GoalTable(
            goal_id=str(goal.goal_id),
            user_id=str(goal.user_id),
            domain=goal.domain.value,
            description=goal.description,
            status=GoalStatus(goal.status).value,
            created_at=goal.created_at,
            target_date=goal.target_date,
        )
    )
    session.commit()
    return goal


@router.get(
    "/plans/history",
    response_model=PlanHistoryResponse,
    summary="Read historical plan versions for a user",
)
def read_plan_history(
    request: Request,
    user_id: UUID,
    session: SessionDependency,
    goal_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PLAN_HISTORY_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlanHistoryResponse:
    ensure_user_access(request, session, user_id)
    _require_profile(session, user_id)
    statement = select(InterventionPlanTable).where(InterventionPlanTable.user_id == str(user_id))
    if goal_id is not None:
        statement = statement.where(InterventionPlanTable.goal_id == str(goal_id))
    plan_rows = session.scalars(
        statement.order_by(
            InterventionPlanTable.start_date.desc(),
            InterventionPlanTable.version.desc(),
            InterventionPlanTable.plan_id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    items: list[PlanHistoryItem] = []
    for plan_row in plan_rows:
        action_rows = session.scalars(
            select(PlanActionTable)
            .where(PlanActionTable.plan_id == plan_row.plan_id)
            .order_by(PlanActionTable.frequency.asc(), PlanActionTable.action_id.asc())
        ).all()
        items.append(
            PlanHistoryItem(
                plan=_plan_from_row(plan_row),
                actions=[_action_from_row(row) for row in action_rows],
            )
        )
    return PlanHistoryResponse(
        items=items,
        limit=limit,
        offset=offset,
        returned_count=len(items),
    )
