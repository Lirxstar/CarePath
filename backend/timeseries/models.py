from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.analysis_quality import AnalysisReliability
from backend.domain.models import MetricType, ObservationUnit


class ChangeDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


class TimeSeriesBaseResult(BaseModel):
    """Shared auditable contract for deterministic CP-005 time-series analytics."""

    model_config = ConfigDict(frozen=True)

    metric: MetricType
    unit: ObservationUnit | None
    start_date: date
    end_date: date
    sample_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    missingness: float = Field(ge=0, le=1)
    suspect_count: int = Field(default=0, ge=0)
    conflicting_count: int = Field(default=0, ge=0)
    reliability: AnalysisReliability
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    source_observation_ids: tuple[UUID, ...] = ()
    used_observation_ids: tuple[UUID, ...] = ()


class PeriodComparisonResult(TimeSeriesBaseResult):
    current_mean: float | None
    baseline_mean: float | None
    absolute_change: float | None
    relative_change: float | None
    percentage_change: float | None
    baseline_start_date: date
    baseline_end_date: date
    baseline_sample_count: int = Field(ge=0)
    baseline_expected_count: int = Field(ge=0)
    baseline_coverage: float = Field(ge=0, le=1)
    baseline_source_observation_ids: tuple[UUID, ...] = ()
    baseline_used_observation_ids: tuple[UUID, ...] = ()


class TrendResult(TimeSeriesBaseResult):
    mean: float | None
    slope_per_day: float | None
    absolute_change: float | None
    relative_change: float | None
    percentage_change: float | None


class RollingMeanPoint(TimeSeriesBaseResult):
    value: float | None
    minimum_observations: int = Field(ge=1)
    minimum_coverage: float = Field(ge=0, le=1)


class MissingnessSummary(TimeSeriesBaseResult):
    observed_observations: int = Field(ge=0)
    valid_observations: int = Field(ge=0)
    missing_observations: int = Field(ge=0)
    explicit_missing_observations: int = Field(ge=0)
    gap_missing_observations: int = Field(ge=0)
    missing_rate: float = Field(ge=0, le=1)


class ChangeSignal(TimeSeriesBaseResult):
    signal_type: str = "behavioural_statistical_change"
    direction: ChangeDirection
    current_mean: float | None
    baseline_mean: float | None
    absolute_change: float | None
    relative_change: float | None
    threshold: float
    threshold_kind: str
    baseline_standard_deviation: float | None
    standardized_change: float | None
    statement: str
