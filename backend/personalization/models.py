from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.analysis_quality import AnalysisReliability


class DifficultyDirection(StrEnum):
    REDUCE = "reduce"
    MAINTAIN = "maintain"
    INCREASE = "increase"


class AdherenceBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion_rate: float | None = Field(default=None, ge=0, le=1)
    scored_feedback_count: int = Field(ge=0)
    total_feedback_count: int = Field(ge=0)


class AdherencePattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern_type: str
    count: int = Field(ge=1)
    domain: str | None = None
    difficulty: str | None = None
    source_action_ids: tuple[UUID, ...] = ()
    source_feedback_ids: tuple[UUID, ...] = ()


class AdherenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion_rate: float | None = Field(default=None, ge=0, le=1)
    completed_count: int = Field(ge=0)
    partially_completed_count: int = Field(ge=0)
    not_completed_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    modified_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    conflicting_count: int = Field(ge=0)
    scored_feedback_count: int = Field(ge=0)
    total_feedback_count: int = Field(ge=0)
    by_domain: dict[str, AdherenceBreakdown]
    by_difficulty: dict[str, AdherenceBreakdown]
    recent: AdherenceBreakdown
    historical_baseline: AdherenceBreakdown
    patterns: tuple[AdherencePattern, ...] = ()
    reliability: AnalysisReliability
    warnings: tuple[str, ...] = ()
    source_goal_ids: tuple[UUID, ...] = ()
    source_plan_ids: tuple[UUID, ...] = ()
    source_action_ids: tuple[UUID, ...] = ()
    source_feedback_ids: tuple[UUID, ...] = ()


class DifficultySignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommended_difficulty_direction: DifficultyDirection
    reason_codes: tuple[str, ...]
    reliability: AnalysisReliability
    supporting_plan_ids: tuple[UUID, ...] = ()
    supporting_action_ids: tuple[UUID, ...] = ()
    supporting_feedback_ids: tuple[UUID, ...] = ()


class PersonalizationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    behavioural_goals: tuple[str, ...]
    schedule_constraints: dict[str, object] | None
    activity_constraints: tuple[str, ...]
    coaching_preferences: dict[str, object] | None
    historical_adherence: float | None = Field(default=None, ge=0, le=1)
    recent_adherence: float | None = Field(default=None, ge=0, le=1)
    current_plan_id: UUID | None
    previous_plan_ids: tuple[UUID, ...]
    adherence_patterns: tuple[AdherencePattern, ...]
    difficulty_signal: DifficultySignal
    source_goal_ids: tuple[UUID, ...]
    source_plan_ids: tuple[UUID, ...]
    source_action_ids: tuple[UUID, ...]
    source_feedback_ids: tuple[UUID, ...]
