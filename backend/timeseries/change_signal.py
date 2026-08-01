from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from statistics import fmean, pstdev
from uuid import UUID

from backend.analysis_quality import assess_reliability
from backend.domain.models import MetricType, ObservationUnit
from backend.timeseries.models import ChangeDirection, ChangeSignal


def compute_change_signal(
    *,
    metric: MetricType,
    unit: ObservationUnit | None,
    start_date: date,
    end_date: date,
    current_values: Sequence[float],
    baseline_values: Sequence[float],
    source_observation_ids: Sequence[UUID] = (),
    expected_count: int | None = None,
    suspect_count: int = 0,
    conflicting_count: int = 0,
    threshold: float = 0.2,
) -> ChangeSignal:
    """Detect a behavioural/statistical change, not a clinical abnormality."""
    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")

    current = fmean(current_values) if current_values else None
    baseline = fmean(baseline_values) if baseline_values else None
    absolute = current - baseline if current is not None and baseline is not None else None
    relative = absolute / baseline if absolute is not None and baseline not in (0, None) else None

    if absolute is None:
        direction = ChangeDirection.INSUFFICIENT_DATA
        statement = "insufficient data for behavioural/statistical change comparison"
        threshold_kind = "relative_change"
    elif relative is None:
        direction = ChangeDirection.INSUFFICIENT_DATA
        statement = "relative change is undefined because the baseline is zero"
        threshold_kind = "relative_change"
    elif abs(relative) >= threshold:
        direction = ChangeDirection.INCREASE if absolute > 0 else ChangeDirection.DECREASE
        statement = "configured behavioural/statistical change threshold reached"
        threshold_kind = "relative_change"
    else:
        direction = ChangeDirection.STABLE
        statement = "configured behavioural/statistical change threshold not reached"
        threshold_kind = "relative_change"

    standard_deviation = pstdev(baseline_values) if len(baseline_values) > 1 else None
    standardized_change = (
        absolute / standard_deviation
        if absolute is not None and standard_deviation not in (None, 0)
        else None
    )
    resolved_expected_count = len(current_values) if expected_count is None else expected_count
    reliability = assess_reliability(
        expected_count=resolved_expected_count,
        valid_count=len(current_values),
        suspect_count=suspect_count,
        conflicting_count=conflicting_count,
        baseline_available=bool(baseline_values),
    )
    coverage = (
        min(1.0, len(current_values) / resolved_expected_count) if resolved_expected_count else 0.0
    )

    return ChangeSignal(
        metric=metric,
        unit=unit,
        start_date=start_date,
        end_date=end_date,
        sample_count=len(current_values),
        expected_count=resolved_expected_count,
        coverage=coverage,
        missingness=1.0 - coverage,
        suspect_count=suspect_count,
        conflicting_count=conflicting_count,
        reliability=reliability,
        warnings=("not_clinical_interpretation",),
        limitations=("behavioural_statistical_signal_only",),
        source_observation_ids=tuple(source_observation_ids),
        used_observation_ids=tuple(source_observation_ids),
        direction=direction,
        current_mean=current,
        baseline_mean=baseline,
        absolute_change=absolute,
        relative_change=relative,
        threshold=threshold,
        threshold_kind=threshold_kind,
        baseline_standard_deviation=standard_deviation,
        standardized_change=standardized_change,
        statement=statement,
    )
