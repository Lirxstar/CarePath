from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Hex = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[0-9a-f]{64}$"),
]


class AgeBand(StrEnum):
    AGE_18_29 = "18-29"
    AGE_30_44 = "30-44"
    AGE_45_64 = "45-64"
    AGE_65_PLUS = "65+"


class Language(StrEnum):
    EN = "en"
    ZH = "zh"
    JA = "ja"


class Domain(StrEnum):
    SLEEP = "sleep"
    PHYSICAL_ACTIVITY = "physical_activity"
    STRESS_MOOD = "stress_mood"
    FALLS_ACTIVITY_SAFETY = "falls_activity_safety"


class MetricType(StrEnum):
    SLEEP_DURATION = "sleep_duration"
    SLEEP_START_TIME = "sleep_start_time"
    SLEEP_END_TIME = "sleep_end_time"
    SLEEP_QUALITY = "sleep_quality"
    STEPS = "steps"
    ACTIVE_MINUTES = "active_minutes"
    RESTING_HEART_RATE = "resting_heart_rate"
    STRESS_SCORE = "stress_score"
    MOOD_SCORE = "mood_score"
    FALL_EVENT = "fall_event"
    NEAR_FALL_EVENT = "near_fall_event"
    ACTIVITY_CONFIDENCE = "activity_confidence"


class ObservationUnit(StrEnum):
    HOURS = "hours"
    MINUTES_SINCE_MIDNIGHT = "minutes_since_midnight"
    SCORE_1_10 = "score_1_10"
    STEPS = "steps"
    MINUTES = "minutes"
    BPM = "bpm"


class SourceType(StrEnum):
    SYNTHETIC_WEARABLE = "synthetic_wearable"
    SELF_REPORT = "self_report"
    CSV = "csv"
    FHIR = "fhir"


class QualityFlag(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    SUSPECT = "suspect"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ActionDifficulty(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    NOT_COMPLETED = "not_completed"


class FeedbackResponse(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    NOT_COMPLETED = "not_completed"


class TrustTier(StrEnum):
    POLICY = "T0_POLICY"
    SAFETY = "T1_SAFETY"
    GUIDELINE = "T2_GUIDELINE"
    OBSERVATION = "T3_OBSERVATION"
    USER_CONTEXT = "T4_USER_CONTEXT"
    MODEL_DRAFT = "T5_MODEL_DRAFT"
    UNTRUSTED_EXTERNAL = "T6_UNTRUSTED_EXTERNAL"


class RiskLevel(StrEnum):
    ROUTINE = "routine"
    CAUTION = "caution"
    URGENT = "urgent"


class InteractionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class AuditEventType(StrEnum):
    SAFETY_DECISION = "safety_decision"
    RETRIEVAL = "retrieval"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLAN_GENERATED = "plan_generated"
    VERIFICATION = "verification"
    PLAN_REVISED = "plan_revised"
    RESPONSE_EMITTED = "response_emitted"


_METRIC_UNITS: dict[MetricType, ObservationUnit | None] = {
    MetricType.SLEEP_DURATION: ObservationUnit.HOURS,
    MetricType.SLEEP_START_TIME: ObservationUnit.MINUTES_SINCE_MIDNIGHT,
    MetricType.SLEEP_END_TIME: ObservationUnit.MINUTES_SINCE_MIDNIGHT,
    MetricType.SLEEP_QUALITY: ObservationUnit.SCORE_1_10,
    MetricType.STEPS: ObservationUnit.STEPS,
    MetricType.ACTIVE_MINUTES: ObservationUnit.MINUTES,
    MetricType.RESTING_HEART_RATE: ObservationUnit.BPM,
    MetricType.STRESS_SCORE: ObservationUnit.SCORE_1_10,
    MetricType.MOOD_SCORE: ObservationUnit.SCORE_1_10,
    MetricType.FALL_EVENT: None,
    MetricType.NEAR_FALL_EVENT: None,
    MetricType.ACTIVITY_CONFIDENCE: ObservationUnit.SCORE_1_10,
}
_BOOLEAN_METRICS = {MetricType.FALL_EVENT, MetricType.NEAR_FALL_EVENT}
_SCORE_METRICS = {
    MetricType.SLEEP_QUALITY,
    MetricType.STRESS_SCORE,
    MetricType.MOOD_SCORE,
    MetricType.ACTIVITY_CONFIDENCE,
}
_TIME_OF_DAY_METRICS = {MetricType.SLEEP_START_TIME, MetricType.SLEEP_END_TIME}


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class UserProfile(Entity):
    user_id: UUID
    age_band: AgeBand
    preferred_language: Language
    timezone: NonEmptyString
    schedule_constraints: dict[str, object] | None = None
    health_goals: list[Domain]
    activity_constraints: list[NonEmptyString] | None = None
    coaching_preferences: dict[str, object] | None = None
    consent_flags: dict[str, bool]

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("health_goals")
    @classmethod
    def unique_health_goals(cls, value: list[Domain]) -> list[Domain]:
        if len(value) != len(set(value)):
            raise ValueError("health_goals must not contain duplicates")
        return value


class Observation(Entity):
    observation_id: UUID
    user_id: UUID
    metric_type: MetricType
    value_numeric: float | None = None
    value_boolean: bool | None = None
    unit: ObservationUnit | None = None
    observed_at: UTCDateTime
    source_type: SourceType
    quality_flag: QualityFlag = QualityFlag.VALID
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, object] | None = None

    @field_validator("value_numeric", mode="before")
    @classmethod
    def reject_boolean_numeric_value(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("value_numeric must not be boolean")
        return value

    @field_validator("value_numeric")
    @classmethod
    def require_finite_numeric_value(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("value_numeric must be finite")
        return value

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        expected_unit = _METRIC_UNITS[self.metric_type]
        if self.unit != expected_unit:
            expected = "null" if expected_unit is None else expected_unit.value
            raise ValueError(f"unit for {self.metric_type.value} must be {expected}")

        value_numeric = self.value_numeric
        value_boolean = self.value_boolean
        if self.quality_flag is QualityFlag.MISSING:
            if value_numeric is not None or value_boolean is not None:
                raise ValueError("missing observations must not contain a value")
            return self

        if self.metric_type in _BOOLEAN_METRICS:
            if value_boolean is None or value_numeric is not None:
                raise ValueError("event observations require value_boolean only")
            return self

        if value_numeric is None or value_boolean is not None:
            raise ValueError("numeric observations require value_numeric only")
        if self.quality_flag is QualityFlag.VALID:
            self._validate_valid_numeric_range(value_numeric)
        return self

    def _validate_valid_numeric_range(self, value: float) -> None:
        if self.metric_type is MetricType.SLEEP_DURATION and not 0 <= value <= 24:
            raise ValueError("sleep_duration must be between 0 and 24 hours")
        if self.metric_type in _TIME_OF_DAY_METRICS and not 0 <= value < 1440:
            raise ValueError("sleep time must be minutes since midnight in [0, 1440)")
        if self.metric_type is MetricType.STEPS and (value < 0 or not value.is_integer()):
            raise ValueError("steps must be a non-negative whole number")
        if self.metric_type is MetricType.ACTIVE_MINUTES and not 0 <= value <= 1440:
            raise ValueError("active_minutes must be between 0 and 1440")
        if self.metric_type is MetricType.RESTING_HEART_RATE and value <= 0:
            raise ValueError("resting_heart_rate must be positive")
        if self.metric_type in _SCORE_METRICS and not 1 <= value <= 10:
            raise ValueError("score metrics must be between 1 and 10")


class JournalEntry(Entity):
    entry_id: UUID
    user_id: UUID
    created_at: UTCDateTime
    text: NonEmptyString
    language: Language
    user_tags: list[NonEmptyString] | None = None


class Goal(Entity):
    goal_id: UUID
    user_id: UUID
    domain: Domain
    description: NonEmptyString
    status: GoalStatus
    created_at: UTCDateTime
    target_date: date | None = None


class InterventionPlan(Entity):
    plan_id: UUID
    user_id: UUID
    goal_id: UUID
    version: int = Field(ge=1)
    start_date: date
    end_date: date
    status: PlanStatus
    generation_interaction_id: UUID
    supersedes_plan_id: UUID | None = None

    @model_validator(mode="after")
    def validate_dates_and_version_link(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.supersedes_plan_id == self.plan_id:
            raise ValueError("a plan cannot supersede itself")
        return self


class PlanAction(Entity):
    action_id: UUID
    plan_id: UUID
    domain: Domain
    description: NonEmptyString
    frequency: NonEmptyString
    difficulty: ActionDifficulty
    rationale: NonEmptyString
    status: ActionStatus


class PlanFeedback(Entity):
    feedback_id: UUID
    action_id: UUID
    user_id: UUID
    response: FeedbackResponse
    completion_ratio: float | None = Field(default=None, ge=0, le=1)
    reason_text: NonEmptyString | None = None
    created_at: UTCDateTime


class KnowledgeSource(Entity):
    source_id: NonEmptyString
    title: NonEmptyString
    organisation: NonEmptyString
    url: NonEmptyString
    published_or_updated_at: date | None = None
    retrieved_at: date
    trust_tier: TrustTier
    licence_note: NonEmptyString

    @field_validator("trust_tier")
    @classmethod
    def require_guideline_trust_tier(cls, value: TrustTier) -> TrustTier:
        if value is not TrustTier.GUIDELINE:
            raise ValueError("KnowledgeSource trust_tier must be T2_GUIDELINE")
        return value


class KnowledgeChunk(Entity):
    chunk_id: NonEmptyString
    source_id: NonEmptyString
    section_title: NonEmptyString | None = None
    content: NonEmptyString
    embedding_model: NonEmptyString
    content_hash: Sha256Hex


class Interaction(Entity):
    interaction_id: UUID
    user_id: UUID
    request_text: NonEmptyString
    language: Language
    started_at: UTCDateTime
    completed_at: UTCDateTime | None = None
    risk_level: RiskLevel
    final_status: InteractionStatus
    response_json: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_completion_state(self) -> Self:
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        if self.final_status is InteractionStatus.IN_PROGRESS and self.completed_at is not None:
            raise ValueError("in_progress interactions must not have completed_at")
        if self.final_status is not InteractionStatus.IN_PROGRESS and self.completed_at is None:
            raise ValueError("finished interactions require completed_at")
        return self


class AuditEvent(Entity):
    audit_event_id: UUID
    interaction_id: UUID
    sequence_number: int = Field(ge=1)
    event_type: AuditEventType
    component: NonEmptyString
    input_refs: dict[str, object]
    output_summary: dict[str, object]
    created_at: UTCDateTime


CarePlan = InterventionPlan
ActionFeedback = PlanFeedback
