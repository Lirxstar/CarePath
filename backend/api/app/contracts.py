from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.agents.response_composer import StructuredCoachResponse
from backend.domain import AuditEvent, InterventionPlan, PlanAction, PlanFeedback
from backend.domain.models import (
    FeedbackResponse,
    InteractionStatus,
    Language,
    MetricType,
    RiskLevel,
)
from backend.timeseries.models import PeriodComparisonResult, TrendResult


class RecordsImportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"


class RecordsImportRequest(BaseModel):
    """JSON transport envelope for the frozen project CSV/JSON import endpoint."""

    model_config = ConfigDict(extra="forbid")

    source_format: RecordsImportFormat
    content: str | dict[str, Any]

    @model_validator(mode="after")
    def validate_content_shape(self) -> RecordsImportRequest:
        if self.source_format is RecordsImportFormat.CSV and not isinstance(self.content, str):
            raise ValueError("csv imports require string content")
        if self.source_format is RecordsImportFormat.JSON and not isinstance(self.content, dict):
            raise ValueError("json imports require object content")
        return self


class FHIRBundleRequest(BaseModel):
    """Deliberately limited FHIR Bundle transport contract."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    resource_type: Literal["Bundle"] = Field(alias="resourceType")
    entry: list[dict[str, Any]] = Field(default_factory=list)


class RecordTrendsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    metric_type: MetricType
    trend: TrendResult
    comparison: PeriodComparisonResult


class CoachMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    message: str = Field(min_length=1, max_length=4_000)
    language: Language = Language.EN


class CoachMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: UUID
    request_id: str
    risk_level: RiskLevel
    status: InteractionStatus
    response_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    verification_disposition: str | None = None
    structured_response: StructuredCoachResponse


class CurrentPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: InterventionPlan
    actions: list[PlanAction]


class PlanFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    action_id: UUID
    response: FeedbackResponse
    completion_ratio: float | None = Field(default=None, ge=0, le=1)
    reason_text: str | None = Field(default=None, min_length=1, max_length=2_000)
    submission_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class PlanFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    feedback: PlanFeedback


class AuditTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: UUID
    events: list[AuditEvent]
