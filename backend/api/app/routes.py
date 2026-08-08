from __future__ import annotations

import json
from datetime import UTC, date, datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents import WorkflowState
from backend.agents.response_composer import StructuredCoachResponse, controlled_safety_response
from backend.agents.response_fallback import controlled_failure_response
from backend.agents.runtime import build_runtime_workflow
from backend.audit import persist_workflow_audit
from backend.domain import AuditEvent, InterventionPlan, Observation, PlanAction, UserProfile
from backend.domain.models import (
    ActionDifficulty,
    ActionStatus,
    AuditEventType,
    Domain,
    InteractionStatus,
    MetricType,
    ObservationUnit,
    PlanStatus,
    QualityFlag,
    SourceType,
)
from backend.imports.csv_importer import CSVHealthImporter
from backend.imports.fhir.parser import FHIRBundleImporter
from backend.imports.json_importer import JSONHealthImporter
from backend.imports.models import ImportReport
from backend.imports.service import ImportService
from backend.personalization.planner import (
    FeedbackSubmissionConflictError,
    InterventionPlanner,
    PlanFeedbackWindowError,
)
from backend.storage.database import get_session
from backend.storage.models import (
    AuditEventTable,
    InteractionTable,
    InterventionPlanTable,
    ObservationTable,
    PlanActionTable,
    UserProfileTable,
)
from backend.timeseries import compare_periods, compute_trend

from .contracts import (
    AuditTraceResponse,
    CoachMessageRequest,
    CoachMessageResponse,
    CurrentPlanResponse,
    FHIRBundleRequest,
    PlanFeedbackRequest,
    PlanFeedbackResponse,
    RecordsImportFormat,
    RecordsImportRequest,
    RecordTrendsResponse,
)
from .errors import CarePathError, get_request_id

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _observation_from_row(row: ObservationTable) -> Observation:
    return Observation(
        observation_id=UUID(row.observation_id),
        user_id=UUID(row.user_id),
        metric_type=MetricType(row.metric_type),
        value_numeric=row.value_numeric,
        value_boolean=row.value_boolean,
        unit=ObservationUnit(row.unit) if row.unit is not None else None,
        observed_at=_as_utc(row.observed_at),
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


def _audit_from_row(row: AuditEventTable) -> AuditEvent:
    return AuditEvent(
        audit_event_id=UUID(row.audit_event_id),
        interaction_id=UUID(row.interaction_id),
        sequence_number=row.sequence_number,
        event_type=AuditEventType(row.event_type),
        component=row.component,
        input_refs=row.input_refs,
        output_summary=row.output_summary,
        created_at=_as_utc(row.created_at),
    )


@router.post(
    "/profiles",
    response_model=UserProfile,
    status_code=HTTPStatus.CREATED,
    summary="Create a CarePath user profile",
)
def create_profile(profile: UserProfile, session: SessionDependency) -> UserProfile:
    if session.get(UserProfileTable, str(profile.user_id)) is not None:
        raise CarePathError(
            "profile_exists",
            "A profile with this user_id already exists",
            status_code=HTTPStatus.CONFLICT,
        )

    session.add(
        UserProfileTable(
            user_id=str(profile.user_id),
            age_band=profile.age_band.value,
            preferred_language=profile.preferred_language.value,
            timezone=profile.timezone,
            schedule_constraints=profile.schedule_constraints,
            health_goals=[item.value for item in profile.health_goals],
            activity_constraints=profile.activity_constraints,
            coaching_preferences=profile.coaching_preferences,
            consent_flags=profile.consent_flags,
        )
    )
    session.commit()
    return profile


@router.post(
    "/records/import",
    response_model=ImportReport,
    summary="Import canonical CarePath CSV or project JSON data",
)
def import_records(payload: RecordsImportRequest, session: SessionDependency) -> ImportReport:
    if payload.source_format is RecordsImportFormat.CSV:
        assert isinstance(payload.content, str)
        prepared = CSVHealthImporter().prepare(payload.content.encode("utf-8"))
    else:
        assert isinstance(payload.content, dict)
        data = json.dumps(payload.content, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        prepared = JSONHealthImporter().prepare(data)
    return ImportService().persist(prepared, session)


@router.post(
    "/fhir/bundle",
    response_model=ImportReport,
    summary="Import the limited CarePath FHIR Bundle subset",
)
def import_fhir_bundle(payload: FHIRBundleRequest, session: SessionDependency) -> ImportReport:
    data = json.dumps(
        payload.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    prepared = FHIRBundleImporter().prepare(data)
    return ImportService().persist(prepared, session)


@router.get(
    "/records/trends",
    response_model=RecordTrendsResponse,
    summary="Return deterministic trend and period-comparison analytics",
)
def records_trends(
    user_id: UUID,
    metric_type: MetricType,
    session: SessionDependency,
    days: Annotated[int, Query(ge=1, le=60)] = 7,
    end_date: date | None = None,
) -> RecordTrendsResponse:
    rows = session.scalars(
        select(ObservationTable)
        .where(
            ObservationTable.user_id == str(user_id),
            ObservationTable.metric_type == metric_type.value,
        )
        .order_by(ObservationTable.observed_at.asc(), ObservationTable.observation_id.asc())
    ).all()
    if not rows:
        raise CarePathError(
            "records_not_found",
            "No observations were found for this user and metric",
            status_code=HTTPStatus.NOT_FOUND,
        )

    observations = [_observation_from_row(row) for row in rows]
    resolved_end_date = end_date or max(item.observed_at.date() for item in observations)
    try:
        trend = compute_trend(
            observations,
            days=days,
            end_date=resolved_end_date,
            metric=metric_type,
        )
        comparison = compare_periods(
            observations,
            end_date=resolved_end_date,
            window_days=days,
            metric=metric_type,
        )
    except ValueError as exc:
        raise CarePathError(
            "invalid_trend_request",
            "Trend analysis could not be computed for the requested window",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc

    return RecordTrendsResponse(
        user_id=user_id,
        metric_type=metric_type,
        trend=trend,
        comparison=comparison,
    )


@router.post(
    "/coach/message",
    response_model=CoachMessageResponse,
    summary="Run one bounded CarePath coaching interaction",
)
def coach_message(
    payload: CoachMessageRequest,
    request: Request,
    session: SessionDependency,
) -> CoachMessageResponse:
    if session.get(UserProfileTable, str(payload.user_id)) is None:
        raise CarePathError(
            "profile_not_found",
            "The requested user profile does not exist",
            status_code=HTTPStatus.NOT_FOUND,
        )

    interaction_id = uuid4()
    state = WorkflowState(
        interaction_id=str(interaction_id),
        user_id=str(payload.user_id),
        request_text=payload.message,
    )
    external_index = getattr(request.app.state, "external_evidence_index", None)
    state = build_runtime_workflow(
        session=session,
        user_id=payload.user_id,
        request_text=payload.message,
        external_index=external_index,
        language=payload.language.value,
    ).run(state)
    risk_level = state.risk_level
    if risk_level is None:
        raise CarePathError(
            "coach_state_invalid",
            "The coaching workflow did not produce a safety disposition",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    raw_structured = state.context.get("structured_response")
    if isinstance(raw_structured, dict):
        structured = StructuredCoachResponse.model_validate(raw_structured)
    elif state.allow_normal_planning is False:
        structured = controlled_safety_response(
            risk_level=risk_level,
            language=payload.language.value,
        )
    else:
        structured = controlled_failure_response(
            risk_level=risk_level,
            language=payload.language.value,
            verification_failed=bool(
                state.verification_disposition is not None
                and state.verification_disposition.value == "fallback"
            ),
        )
    state.context["structured_response"] = structured.model_dump(mode="json")
    state.response_text = structured.rendered_text

    status = InteractionStatus(state.status.value)
    evidence_ids = [source.evidence_id for source in structured.sources]
    verification = (
        state.verification_disposition.value if state.verification_disposition is not None else None
    )
    response = CoachMessageResponse(
        interaction_id=interaction_id,
        request_id=get_request_id(request),
        risk_level=risk_level,
        status=status,
        response_text=structured.rendered_text,
        evidence_ids=evidence_ids,
        verification_disposition=verification,
        structured_response=structured,
    )

    now = datetime.now(UTC)
    session.add(
        InteractionTable(
            interaction_id=str(interaction_id),
            user_id=str(payload.user_id),
            request_text=payload.message,
            language=payload.language.value,
            started_at=now,
            completed_at=now,
            risk_level=risk_level.value,
            final_status=status.value,
            response_json=response.model_dump(mode="json"),
        )
    )
    session.flush()
    persist_workflow_audit(session, state, created_at=now)
    session.commit()
    return response


@router.get(
    "/plans/current",
    response_model=CurrentPlanResponse,
    summary="Return the latest active, in-window plan for a user",
)
def current_plan(
    user_id: UUID,
    session: SessionDependency,
    goal_id: UUID | None = None,
) -> CurrentPlanResponse:
    today = datetime.now(UTC).date()
    statement = select(InterventionPlanTable).where(
        InterventionPlanTable.user_id == str(user_id),
        InterventionPlanTable.status == PlanStatus.ACTIVE.value,
        InterventionPlanTable.start_date <= today,
        InterventionPlanTable.end_date >= today,
    )
    if goal_id is not None:
        statement = statement.where(InterventionPlanTable.goal_id == str(goal_id))
    row = session.scalars(
        statement.order_by(
            InterventionPlanTable.start_date.desc(),
            InterventionPlanTable.version.desc(),
            InterventionPlanTable.plan_id.desc(),
        )
    ).first()
    if row is None:
        raise CarePathError(
            "plan_not_found",
            "No active plan in the current date window was found for this user",
            status_code=HTTPStatus.NOT_FOUND,
        )

    action_rows = session.scalars(
        select(PlanActionTable)
        .where(PlanActionTable.plan_id == row.plan_id)
        .order_by(PlanActionTable.frequency.asc(), PlanActionTable.action_id.asc())
    ).all()
    return CurrentPlanResponse(
        plan=_plan_from_row(row),
        actions=[_action_from_row(action) for action in action_rows],
    )


@router.post(
    "/plans/{plan_id}/feedback",
    response_model=PlanFeedbackResponse,
    status_code=HTTPStatus.CREATED,
    summary="Record idempotent structured feedback for an active plan action",
)
def plan_feedback(
    plan_id: UUID,
    payload: PlanFeedbackRequest,
    session: SessionDependency,
) -> PlanFeedbackResponse:
    plan = session.get(InterventionPlanTable, str(plan_id))
    if plan is None or plan.user_id != str(payload.user_id):
        raise CarePathError(
            "plan_not_found",
            "The requested plan does not exist for this user",
            status_code=HTTPStatus.NOT_FOUND,
        )
    action = session.get(PlanActionTable, str(payload.action_id))
    if action is None or action.plan_id != str(plan_id):
        raise CarePathError(
            "action_not_found",
            "The requested action does not belong to this plan",
            status_code=HTTPStatus.NOT_FOUND,
        )

    try:
        feedback = InterventionPlanner(session).record_feedback(
            action_id=payload.action_id,
            user_id=payload.user_id,
            response=payload.response,
            completion_ratio=payload.completion_ratio,
            reason_text=payload.reason_text,
            submission_key=payload.submission_key,
        )
    except PlanFeedbackWindowError as exc:
        raise CarePathError(
            exc.code,
            str(exc),
            status_code=HTTPStatus.CONFLICT,
        ) from exc
    except FeedbackSubmissionConflictError as exc:
        raise CarePathError(
            "feedback_idempotency_conflict",
            str(exc),
            status_code=HTTPStatus.CONFLICT,
        ) from exc
    session.commit()
    return PlanFeedbackResponse(plan_id=plan_id, feedback=feedback)


@router.get(
    "/audit/{interaction_id}",
    response_model=AuditTraceResponse,
    summary="Return audit events currently persisted for an interaction",
)
def audit_trace(interaction_id: UUID, session: SessionDependency) -> AuditTraceResponse:
    if session.get(InteractionTable, str(interaction_id)) is None:
        raise CarePathError(
            "interaction_not_found",
            "The requested interaction does not exist",
            status_code=HTTPStatus.NOT_FOUND,
        )
    rows = session.scalars(
        select(AuditEventTable)
        .where(AuditEventTable.interaction_id == str(interaction_id))
        .order_by(AuditEventTable.sequence_number.asc())
    ).all()
    return AuditTraceResponse(
        interaction_id=interaction_id,
        events=[_audit_from_row(row) for row in rows],
    )
