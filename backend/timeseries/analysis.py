from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import fmean
from uuid import UUID

from backend.analysis_quality import AnalysisReliability, assess_reliability
from backend.domain.models import MetricType, Observation, ObservationUnit, QualityFlag
from backend.timeseries.config import UNIT_BY_METRIC, expected_count
from backend.timeseries.models import (
    MissingnessSummary,
    PeriodComparisonResult,
    RollingMeanPoint,
    TrendResult,
)

_SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True)
class _UsablePoint:
    observed_at: datetime
    value: float
    observation_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class _WindowStats:
    metric: MetricType
    unit: ObservationUnit | None
    start_date: date
    end_date: date
    expected_count: int
    all_observation_ids: tuple[UUID, ...]
    points: tuple[_UsablePoint, ...]
    suspect_count: int
    conflicting_count: int
    explicit_missing_count: int
    gap_missing_count: int
    warnings: tuple[str, ...]

    @property
    def sample_count(self) -> int:
        return len(self.points)

    @property
    def coverage(self) -> float:
        if self.expected_count == 0:
            return 0.0
        return min(1.0, self.sample_count / self.expected_count)

    @property
    def missingness(self) -> float:
        return 1.0 - self.coverage

    @property
    def used_observation_ids(self) -> tuple[UUID, ...]:
        return tuple(identifier for point in self.points for identifier in point.observation_ids)


def _validate_window(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")


def _metric_observations(
    observations: Sequence[Observation], metric: MetricType | None
) -> tuple[MetricType, list[Observation]]:
    if metric is None:
        if not observations:
            raise ValueError("metric is required when observations are empty")
        metrics = {item.metric_type for item in observations}
        if len(metrics) != 1:
            raise ValueError("metric is required for mixed-metric observations")
        metric = next(iter(metrics))
    return metric, [item for item in observations if item.metric_type is metric]


def _deduplicate(observations: Sequence[Observation]) -> list[Observation]:
    by_id: dict[UUID, Observation] = {}
    for item in observations:
        previous = by_id.get(item.observation_id)
        if previous is None:
            by_id[item.observation_id] = item
        elif previous != item:
            raise ValueError("duplicate observation_id has conflicting content")
    return sorted(by_id.values(), key=lambda item: (item.observed_at, str(item.observation_id)))


def _has_contextual_contradiction(item: Observation) -> bool:
    return item.metadata is not None and bool(item.metadata.get("contradiction_id"))


def _window_stats(
    observations: Sequence[Observation],
    *,
    metric: MetricType | None,
    start_date: date,
    end_date: date,
    numeric_required: bool,
) -> _WindowStats:
    _validate_window(start_date, end_date)
    metric, metric_items = _metric_observations(observations, metric)
    unit = UNIT_BY_METRIC[metric]
    if numeric_required and unit is None:
        raise ValueError(f"{metric.value} is not a numeric metric")

    unique = _deduplicate(metric_items)
    in_window = [item for item in unique if start_date <= item.observed_at.date() <= end_date]
    by_day: dict[date, list[Observation]] = defaultdict(list)
    for item in in_window:
        if item.unit != unit:
            raise ValueError(f"incompatible unit for {metric.value}")
        by_day[item.observed_at.date()].append(item)

    points: list[_UsablePoint] = []
    suspect_count = 0
    conflicting_count = 0
    explicit_missing_count = 0
    gap_missing_count = 0
    warnings: set[str] = set()
    current = start_date
    while current <= end_date:
        records = by_day.get(current, [])
        if not records:
            gap_missing_count += 1
            current += timedelta(days=1)
            continue

        suspect_count += sum(item.quality_flag is QualityFlag.SUSPECT for item in records)
        explicit_missing_count += sum(item.quality_flag is QualityFlag.MISSING for item in records)
        contextual = sum(_has_contextual_contradiction(item) for item in records)
        if contextual:
            conflicting_count += contextual
            warnings.add("contextual_contradiction_present")

        valid = [
            item
            for item in records
            if item.quality_flag is QualityFlag.VALID and item.value_numeric is not None
        ]
        distinct_values = {
            float(item.value_numeric) for item in valid if item.value_numeric is not None
        }
        if len(distinct_values) > 1:
            conflicting_count += len(valid)
            warnings.add("conflicting_daily_values_excluded")
        elif valid:
            representative = min(
                valid, key=lambda item: (item.observed_at, str(item.observation_id))
            )
            assert representative.value_numeric is not None
            points.append(
                _UsablePoint(
                    observed_at=representative.observed_at,
                    value=float(representative.value_numeric),
                    observation_ids=tuple(item.observation_id for item in valid),
                )
            )
        current += timedelta(days=1)

    if suspect_count:
        warnings.add("suspect_observations_excluded")
    if explicit_missing_count:
        warnings.add("explicit_missing_observations")
    if gap_missing_count:
        warnings.add("calendar_gaps_detected")

    days = (end_date - start_date).days + 1
    return _WindowStats(
        metric=metric,
        unit=unit,
        start_date=start_date,
        end_date=end_date,
        expected_count=expected_count(metric, days),
        all_observation_ids=tuple(item.observation_id for item in in_window),
        points=tuple(points),
        suspect_count=suspect_count,
        conflicting_count=conflicting_count,
        explicit_missing_count=explicit_missing_count,
        gap_missing_count=gap_missing_count,
        warnings=tuple(sorted(warnings)),
    )


def _reliability(
    stats: _WindowStats, *, minimum_samples: int = 3, baseline: bool = True
) -> AnalysisReliability:
    return assess_reliability(
        expected_count=stats.expected_count,
        valid_count=stats.sample_count,
        suspect_count=stats.suspect_count,
        conflicting_count=stats.conflicting_count,
        minimum_samples=minimum_samples,
        baseline_available=baseline,
    )


def _relative_change(
    current: float | None, baseline: float | None
) -> tuple[float | None, float | None]:
    if current is None or baseline is None or baseline == 0:
        return None, None
    relative = (current - baseline) / baseline
    return relative, relative * 100.0


def compare_periods(
    observations: Sequence[Observation],
    end_date: date,
    window_days: int = 7,
    baseline_days: int | None = None,
    *,
    baseline_end_date: date | None = None,
    metric: MetricType | None = None,
) -> PeriodComparisonResult:
    """Compare a recent daily window with the previous or configured baseline window."""
    if window_days < 1:
        raise ValueError("window_days must be positive")
    baseline_days = window_days if baseline_days is None else baseline_days
    if baseline_days < 1:
        raise ValueError("baseline_days must be positive")

    start_date = end_date - timedelta(days=window_days - 1)
    baseline_end = baseline_end_date or (start_date - timedelta(days=1))
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    recent = _window_stats(
        observations,
        metric=metric,
        start_date=start_date,
        end_date=end_date,
        numeric_required=True,
    )
    baseline = _window_stats(
        observations,
        metric=recent.metric,
        start_date=baseline_start,
        end_date=baseline_end,
        numeric_required=True,
    )

    current_mean = fmean(point.value for point in recent.points) if recent.points else None
    baseline_mean = fmean(point.value for point in baseline.points) if baseline.points else None
    absolute = (
        current_mean - baseline_mean
        if current_mean is not None and baseline_mean is not None
        else None
    )
    relative, percentage = _relative_change(current_mean, baseline_mean)
    warnings = set(recent.warnings) | {f"baseline:{item}" for item in baseline.warnings}
    if baseline_mean == 0 and current_mean is not None:
        warnings.add("relative_change_undefined_zero_baseline")
    if baseline_mean is None:
        warnings.add("baseline_unavailable")

    return PeriodComparisonResult(
        metric=recent.metric,
        unit=recent.unit,
        start_date=start_date,
        end_date=end_date,
        sample_count=recent.sample_count,
        expected_count=recent.expected_count,
        coverage=recent.coverage,
        missingness=recent.missingness,
        suspect_count=recent.suspect_count,
        conflicting_count=recent.conflicting_count,
        reliability=_reliability(recent, baseline=baseline.sample_count > 0),
        warnings=tuple(sorted(warnings)),
        source_observation_ids=recent.all_observation_ids,
        used_observation_ids=recent.used_observation_ids,
        current_mean=current_mean,
        baseline_mean=baseline_mean,
        absolute_change=absolute,
        relative_change=relative,
        percentage_change=percentage,
        baseline_start_date=baseline_start,
        baseline_end_date=baseline_end,
        baseline_sample_count=baseline.sample_count,
        baseline_expected_count=baseline.expected_count,
        baseline_coverage=baseline.coverage,
        baseline_source_observation_ids=baseline.all_observation_ids,
        baseline_used_observation_ids=baseline.used_observation_ids,
    )


def compute_trend(
    observations: Sequence[Observation],
    days: int = 7,
    *,
    end_date: date | None = None,
    metric: MetricType | None = None,
) -> TrendResult:
    """Compute a mean and linear slope using elapsed time in real days."""
    if days < 1:
        raise ValueError("days must be positive")
    metric, metric_items = _metric_observations(observations, metric)
    if end_date is None:
        if not metric_items:
            raise ValueError("end_date is required when observations are empty")
        end_date = max(item.observed_at.date() for item in metric_items)
    start_date = end_date - timedelta(days=days - 1)
    stats = _window_stats(
        metric_items,
        metric=metric,
        start_date=start_date,
        end_date=end_date,
        numeric_required=True,
    )
    values = [point.value for point in stats.points]
    mean = fmean(values) if values else None
    slope: float | None = None
    absolute: float | None = None
    relative: float | None = None
    percentage: float | None = None
    warnings = set(stats.warnings)

    if len(stats.points) >= 2:
        origin = stats.points[0].observed_at
        xs = [
            (point.observed_at - origin).total_seconds() / _SECONDS_PER_DAY
            for point in stats.points
        ]
        mean_x = fmean(xs)
        mean_y = fmean(values)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        slope = (
            0.0
            if denominator == 0
            else sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True))
            / denominator
        )
        absolute = values[-1] - values[0]
        relative, percentage = _relative_change(values[-1], values[0])
        if values[0] == 0:
            warnings.add("relative_change_undefined_zero_start")
    else:
        warnings.add("trend_requires_two_points")

    return TrendResult(
        metric=stats.metric,
        unit=stats.unit,
        start_date=start_date,
        end_date=end_date,
        sample_count=stats.sample_count,
        expected_count=stats.expected_count,
        coverage=stats.coverage,
        missingness=stats.missingness,
        suspect_count=stats.suspect_count,
        conflicting_count=stats.conflicting_count,
        reliability=_reliability(stats),
        warnings=tuple(sorted(warnings)),
        source_observation_ids=stats.all_observation_ids,
        used_observation_ids=stats.used_observation_ids,
        mean=mean,
        slope_per_day=slope,
        absolute_change=absolute,
        relative_change=relative,
        percentage_change=percentage,
    )


def rolling_mean(
    observations: Sequence[Observation],
    window_days: int = 7,
    *,
    metric: MetricType | None = None,
    minimum_observations: int = 2,
    minimum_coverage: float = 0.5,
) -> list[RollingMeanPoint]:
    """Return one deterministic trailing-window mean for each calendar day in the metric series."""
    if window_days < 1:
        raise ValueError("window_days must be positive")
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    if not 0 <= minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be between 0 and 1")
    if not observations:
        return []

    metric, metric_items = _metric_observations(observations, metric)
    if not metric_items:
        return []
    unique = _deduplicate(metric_items)
    first_day = min(item.observed_at.date() for item in unique)
    final_day = max(item.observed_at.date() for item in unique)
    result: list[RollingMeanPoint] = []
    current = first_day
    while current <= final_day:
        start = current - timedelta(days=window_days - 1)
        stats = _window_stats(
            unique,
            metric=metric,
            start_date=start,
            end_date=current,
            numeric_required=True,
        )
        policy_met = (
            stats.sample_count >= minimum_observations and stats.coverage >= minimum_coverage
        )
        value = (
            fmean(point.value for point in stats.points) if stats.points and policy_met else None
        )
        warnings = set(stats.warnings)
        if not policy_met:
            warnings.add("rolling_policy_not_met")
        result.append(
            RollingMeanPoint(
                metric=stats.metric,
                unit=stats.unit,
                start_date=start,
                end_date=current,
                sample_count=stats.sample_count,
                expected_count=stats.expected_count,
                coverage=stats.coverage,
                missingness=stats.missingness,
                suspect_count=stats.suspect_count,
                conflicting_count=stats.conflicting_count,
                reliability=_reliability(stats, minimum_samples=minimum_observations),
                warnings=tuple(sorted(warnings)),
                source_observation_ids=stats.all_observation_ids,
                used_observation_ids=stats.used_observation_ids,
                value=value,
                minimum_observations=minimum_observations,
                minimum_coverage=minimum_coverage,
            )
        )
        current += timedelta(days=1)
    return result


def summarise_missingness(
    observations: Sequence[Observation],
    start_date: date,
    end_date: date,
    *,
    metric: MetricType | None = None,
) -> MissingnessSummary:
    """Summarise explicit missing records and absent expected calendar slots."""
    stats = _window_stats(
        observations,
        metric=metric,
        start_date=start_date,
        end_date=end_date,
        numeric_required=False,
    )
    _, metric_items = _metric_observations(observations, stats.metric)
    in_window = _deduplicate(
        [item for item in metric_items if start_date <= item.observed_at.date() <= end_date]
    )
    valid_records = sum(item.quality_flag is QualityFlag.VALID for item in in_window)
    missing_slots = max(0, stats.expected_count - stats.sample_count)

    return MissingnessSummary(
        metric=stats.metric,
        unit=stats.unit,
        start_date=start_date,
        end_date=end_date,
        sample_count=stats.sample_count,
        expected_count=stats.expected_count,
        coverage=stats.coverage,
        missingness=stats.missingness,
        suspect_count=stats.suspect_count,
        conflicting_count=stats.conflicting_count,
        reliability=_reliability(stats),
        warnings=stats.warnings,
        source_observation_ids=stats.all_observation_ids,
        used_observation_ids=stats.used_observation_ids,
        observed_observations=len(in_window),
        valid_observations=valid_records,
        missing_observations=missing_slots,
        explicit_missing_observations=stats.explicit_missing_count,
        gap_missing_observations=stats.gap_missing_count,
        missing_rate=stats.missingness,
    )
