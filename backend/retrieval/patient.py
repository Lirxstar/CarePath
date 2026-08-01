"""User-scoped Patient Evidence retrieval with bounded time windows and analytics-first facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.analysis_quality import AnalysisReliability, ReliabilityLevel, assess_reliability
from backend.domain import Observation
from backend.domain.models import MetricType, ObservationUnit, QualityFlag, SourceType
from backend.storage.models import (
    GoalTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    UserProfileTable,
)
from backend.timeseries import compute_trend
from backend.timeseries.config import UNIT_BY_METRIC

MAX_PATIENT_EVIDENCE_RANGE = timedelta(days=366)
MAX_TEXT_EVIDENCE_ITEMS = 5
MAX_PLAN_EVIDENCE_ITEMS = 5


class PatientEvidenceKind(StrEnum):
    STRUCTURED_FACT = "structured_fact"
    SUBJECTIVE_DESCRIPTION = "subjective_description"
    CONTEXT_RECORD = "context_record"


class PatientEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    kind: PatientEvidenceKind
    fact: str
    source_record_ids: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None
    reliability: AnalysisReliability
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PatientEvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    window_days: Literal[7, 30] | None = 7
    start_at: datetime | None = None
    end_at: datetime | None = None
    metric_types: tuple[MetricType, ...] = ()
    keyword: str | None = Field(default=None, min_length=1, max_length=200)
    include_profile: bool = True
    include_journals: bool = True
    include_goals: bool = True
    include_plans: bool = True

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("patient evidence timestamps must include a timezone")
        return value.astimezone(UTC)

    @field_validator("metric_types")
    @classmethod
    def unique_metrics(cls, value: tuple[MetricType, ...]) -> tuple[MetricType, ...]:
        if len(value) != len(set(value)):
            raise ValueError("metric_types must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> PatientEvidenceQuery:
        if self.start_at is not None:
            if self.window_days is not None:
                raise ValueError("explicit start_at requires window_days=null")
            if self.end_at is None:
                raise ValueError("explicit start_at requires end_at")
            if self.end_at < self.start_at:
                raise ValueError("end_at must not be before start_at")
            if self.end_at - self.start_at > MAX_PATIENT_EVIDENCE_RANGE:
                raise ValueError("patient evidence range is limited to 366 days")
        elif self.window_days is None:
            raise ValueError("window_days is required when start_at is not provided")
        return self

    def resolved_window(self, *, now: datetime | None = None) -> tuple[datetime, datetime]:
        end = self.end_at or now or datetime.now(UTC)
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError("resolved end time must include a timezone")
        end = end.astimezone(UTC)
        if self.start_at is not None:
            return self.start_at, end
        assert self.window_days is not None
        start = end - timedelta(days=self.window_days - 1)
        return start, end


class PatientEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    start_at: datetime
    end_at: datetime
    items: tuple[PatientEvidenceItem, ...]

    @property
    def structured_facts(self) -> tuple[PatientEvidenceItem, ...]:
        return tuple(
            item for item in self.items if item.kind is PatientEvidenceKind.STRUCTURED_FACT
        )

    @property
    def subjective_descriptions(self) -> tuple[PatientEvidenceItem, ...]:
        return tuple(
            item for item in self.items if item.kind is PatientEvidenceKind.SUBJECTIVE_DESCRIPTION
        )


class PatientEvidenceService:
    """Build Patient Evidence from one user's persisted records without cross-user candidates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve(
        self,
        query: PatientEvidenceQuery,
        *,
        now: datetime | None = None,
    ) -> PatientEvidenceResponse:
        profile = self.session.get(UserProfileTable, str(query.user_id))
        if profile is None:
            raise ValueError("patient profile does not exist")
        start_at, end_at = query.resolved_window(now=now)
        items: list[PatientEvidenceItem] = []

        if query.include_profile:
            items.append(self._profile_evidence(profile))
        items.extend(self._observation_evidence(query, start_at=start_at, end_at=end_at))
        if query.include_journals:
            items.extend(self._journal_evidence(query, start_at=start_at, end_at=end_at))
        if query.include_goals:
            items.extend(self._goal_evidence(query))
        if query.include_plans:
            items.extend(self._plan_evidence(query, start_at=start_at, end_at=end_at))

        return PatientEvidenceResponse(
            user_id=query.user_id,
            start_at=start_at,
            end_at=end_at,
            items=tuple(items),
        )

    def _profile_evidence(self, row: UserProfileTable) -> PatientEvidenceItem:
        schedule_keys = sorted((row.schedule_constraints or {}).keys())
        preference_keys = sorted((row.coaching_preferences or {}).keys())
        fact = (
            "Profile context: health goals="
            + ", ".join(row.health_goals)
            + f"; timezone={row.timezone}; schedule fields={', '.join(schedule_keys) or 'none'}; "
            + f"coaching preference fields={', '.join(preference_keys) or 'none'}."
        )
        return PatientEvidenceItem(
            evidence_id=f"patient:profile:{row.user_id}",
            kind=PatientEvidenceKind.CONTEXT_RECORD,
            fact=fact,
            source_record_ids=(row.user_id,),
            reliability=_record_reliability("persisted_profile"),
            metadata={"record_type": "profile"},
        )

    def _observation_evidence(
        self,
        query: PatientEvidenceQuery,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[PatientEvidenceItem]:
        statement = select(ObservationTable).where(
            ObservationTable.user_id == str(query.user_id),
            ObservationTable.observed_at >= start_at,
            ObservationTable.observed_at <= end_at,
        )
        if query.metric_types:
            statement = statement.where(
                ObservationTable.metric_type.in_([item.value for item in query.metric_types])
            )
        rows = self.session.scalars(
            statement.order_by(ObservationTable.observed_at.asc(), ObservationTable.observation_id)
        ).all()
        grouped: dict[MetricType, list[Observation]] = defaultdict(list)
        for row in rows:
            grouped[MetricType(row.metric_type)].append(_observation_from_row(row))

        window_days = (end_at.date() - start_at.date()).days + 1
        evidence: list[PatientEvidenceItem] = []
        for metric in sorted(grouped, key=lambda item: item.value):
            observations = grouped[metric]
            if UNIT_BY_METRIC[metric] is None:
                evidence.append(
                    self._event_fact(
                        metric, observations, start_at.date(), end_at.date(), window_days
                    )
                )
                continue
            trend = compute_trend(
                observations,
                days=window_days,
                end_date=end_at.date(),
                metric=metric,
            )
            unit = trend.unit.value if trend.unit is not None else "unitless"
            mean_text = "unavailable" if trend.mean is None else f"{trend.mean:.3g} {unit}"
            slope_text = (
                "unavailable"
                if trend.slope_per_day is None
                else f"{trend.slope_per_day:.3g} {unit}/day"
            )
            fact = (
                f"{metric.value} from {trend.start_date.isoformat()} to "
                f"{trend.end_date.isoformat()}: "
                f"{trend.sample_count}/{trend.expected_count} usable daily observations; "
                f"mean={mean_text}; slope={slope_text}."
            )
            evidence.append(
                PatientEvidenceItem(
                    evidence_id=(
                        f"patient:trend:{query.user_id}:{metric.value}:"
                        f"{trend.start_date.isoformat()}:{trend.end_date.isoformat()}"
                    ),
                    kind=PatientEvidenceKind.STRUCTURED_FACT,
                    fact=fact,
                    source_record_ids=tuple(str(item) for item in trend.source_observation_ids),
                    start_date=trend.start_date,
                    end_date=trend.end_date,
                    reliability=trend.reliability,
                    metadata={
                        "record_type": "observation_summary",
                        "metric_type": metric.value,
                        "sample_count": trend.sample_count,
                        "expected_count": trend.expected_count,
                        "coverage": trend.coverage,
                    },
                )
            )
        return evidence

    def _event_fact(
        self,
        metric: MetricType,
        observations: list[Observation],
        start_date: date,
        end_date: date,
        expected_count: int,
    ) -> PatientEvidenceItem:
        usable = [
            item
            for item in observations
            if item.quality_flag is QualityFlag.VALID and item.value_boolean is not None
        ]
        event_count = sum(item.value_boolean is True for item in usable)
        suspect_count = sum(item.quality_flag is QualityFlag.SUSPECT for item in observations)
        reliability = assess_reliability(
            expected_count=expected_count,
            valid_count=len(usable),
            suspect_count=suspect_count,
        )
        return PatientEvidenceItem(
            evidence_id=f"patient:event:{metric.value}:{start_date.isoformat()}:{end_date.isoformat()}",
            kind=PatientEvidenceKind.STRUCTURED_FACT,
            fact=(
                f"{metric.value} from {start_date.isoformat()} to {end_date.isoformat()}: "
                f"{event_count} recorded true events across {len(usable)} usable daily records."
            ),
            source_record_ids=tuple(str(item.observation_id) for item in observations),
            start_date=start_date,
            end_date=end_date,
            reliability=reliability,
            metadata={
                "record_type": "observation_summary",
                "metric_type": metric.value,
                "event_count": event_count,
            },
        )

    def _journal_evidence(
        self,
        query: PatientEvidenceQuery,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[PatientEvidenceItem]:
        rows = self.session.scalars(
            select(JournalEntryTable)
            .where(
                JournalEntryTable.user_id == str(query.user_id),
                JournalEntryTable.created_at >= start_at,
                JournalEntryTable.created_at <= end_at,
            )
            .order_by(JournalEntryTable.created_at.desc(), JournalEntryTable.entry_id)
        ).all()
        keyword = query.keyword.casefold() if query.keyword else None
        selected = [row for row in rows if keyword is None or keyword in row.text.casefold()]
        evidence: list[PatientEvidenceItem] = []
        for row in selected[:MAX_TEXT_EVIDENCE_ITEMS]:
            created_at = _as_utc(row.created_at)
            evidence.append(
                PatientEvidenceItem(
                    evidence_id=f"patient:journal:{row.entry_id}",
                    kind=PatientEvidenceKind.SUBJECTIVE_DESCRIPTION,
                    fact=row.text,
                    source_record_ids=(row.entry_id,),
                    start_date=created_at.date(),
                    end_date=created_at.date(),
                    reliability=AnalysisReliability(
                        level=ReliabilityLevel.MEDIUM,
                        reason_codes=("self_report_subjective",),
                    ),
                    metadata={"record_type": "journal", "language": row.language},
                )
            )
        return evidence

    def _goal_evidence(self, query: PatientEvidenceQuery) -> list[PatientEvidenceItem]:
        rows = self.session.scalars(
            select(GoalTable)
            .where(GoalTable.user_id == str(query.user_id))
            .order_by(GoalTable.created_at.desc(), GoalTable.goal_id)
        ).all()
        keyword = query.keyword.casefold() if query.keyword else None
        selected = [
            row
            for row in rows
            if keyword is None
            or keyword in row.description.casefold()
            or keyword in row.domain.casefold()
        ]
        return [
            PatientEvidenceItem(
                evidence_id=f"patient:goal:{row.goal_id}",
                kind=PatientEvidenceKind.CONTEXT_RECORD,
                fact=f"Goal ({row.status}, {row.domain}): {row.description}",
                source_record_ids=(row.goal_id,),
                start_date=_as_utc(row.created_at).date(),
                end_date=row.target_date,
                reliability=_record_reliability("persisted_goal"),
                metadata={"record_type": "goal", "domain": row.domain, "status": row.status},
            )
            for row in selected[:MAX_TEXT_EVIDENCE_ITEMS]
        ]

    def _plan_evidence(
        self,
        query: PatientEvidenceQuery,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[PatientEvidenceItem]:
        rows = self.session.scalars(
            select(InterventionPlanTable)
            .where(
                InterventionPlanTable.user_id == str(query.user_id),
                InterventionPlanTable.start_date <= end_at.date(),
                InterventionPlanTable.end_date >= start_at.date(),
            )
            .order_by(
                InterventionPlanTable.start_date.desc(),
                InterventionPlanTable.version.desc(),
                InterventionPlanTable.plan_id,
            )
        ).all()
        keyword = query.keyword.casefold() if query.keyword else None
        evidence: list[PatientEvidenceItem] = []
        for row in rows:
            actions = self.session.scalars(
                select(PlanActionTable)
                .where(PlanActionTable.plan_id == row.plan_id)
                .order_by(PlanActionTable.action_id)
            ).all()
            searchable = " ".join(
                [
                    row.status,
                    *(action.domain for action in actions),
                    *(action.description for action in actions),
                ]
            ).casefold()
            if keyword is not None and keyword not in searchable:
                continue
            action_summary = (
                "; ".join(action.description[:160] for action in actions[:3]) or "no actions"
            )
            evidence.append(
                PatientEvidenceItem(
                    evidence_id=f"patient:plan:{row.plan_id}",
                    kind=PatientEvidenceKind.CONTEXT_RECORD,
                    fact=(
                        f"Plan v{row.version} ({row.status}) {row.start_date.isoformat()} to "
                        f"{row.end_date.isoformat()}: {action_summary}."
                    ),
                    source_record_ids=(row.plan_id, *(action.action_id for action in actions)),
                    start_date=row.start_date,
                    end_date=row.end_date,
                    reliability=_record_reliability("persisted_plan"),
                    metadata={
                        "record_type": "plan",
                        "status": row.status,
                        "version": row.version,
                        "action_count": len(actions),
                    },
                )
            )
            if len(evidence) >= MAX_PLAN_EVIDENCE_ITEMS:
                break
        return evidence


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


def _record_reliability(reason: str) -> AnalysisReliability:
    return AnalysisReliability(level=ReliabilityLevel.HIGH, reason_codes=(reason,))
