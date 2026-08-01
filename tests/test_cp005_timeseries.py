from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.analysis_quality import ReliabilityLevel
from backend.domain.models import (
    MetricType,
    Observation,
    ObservationUnit,
    QualityFlag,
    SourceType,
)
from backend.timeseries.analysis import (
    compare_periods,
    compute_trend,
    rolling_mean,
    summarise_missingness,
)

USER_ID = UUID("10000000-0000-0000-0000-000000000001")
START = datetime(2026, 1, 1, 8, tzinfo=UTC)


def _obs(
    day_index: int,
    value: float | None,
    flag: QualityFlag = QualityFlag.VALID,
    *,
    metric: MetricType = MetricType.STEPS,
    observed_hour: int = 8,
    metadata: dict[str, object] | None = None,
) -> Observation:
    unit_by_metric = {
        MetricType.STEPS: ObservationUnit.STEPS,
        MetricType.SLEEP_DURATION: ObservationUnit.HOURS,
        MetricType.STRESS_SCORE: ObservationUnit.SCORE_1_10,
    }
    return Observation(
        observation_id=uuid4(),
        user_id=USER_ID,
        metric_type=metric,
        value_numeric=value,
        unit=unit_by_metric[metric],
        observed_at=(START + timedelta(days=day_index)).replace(hour=observed_hour),
        source_type=SourceType.SYNTHETIC_WEARABLE,
        quality_flag=flag,
        metadata=metadata,
    )


def test_compare_periods_detects_change_and_keeps_provenance() -> None:
    items = [_obs(day, 100) for day in range(7)] + [_obs(day, 200) for day in range(7, 14)]
    result = compare_periods(items, date(2026, 1, 14))

    assert result.current_mean == 200
    assert result.baseline_mean == 100
    assert result.absolute_change == 100
    assert result.relative_change == 1
    assert result.percentage_change == 100
    assert len(result.source_observation_ids) == 7
    assert len(result.baseline_source_observation_ids) == 7
    assert result.reliability.level is ReliabilityLevel.HIGH


def test_compare_periods_zero_baseline_does_not_fake_percentage() -> None:
    items = [_obs(day, 0) for day in range(7)] + [_obs(day, 10) for day in range(7, 14)]
    result = compare_periods(items, date(2026, 1, 14))

    assert result.absolute_change == 10
    assert result.relative_change is None
    assert result.percentage_change is None
    assert "relative_change_undefined_zero_baseline" in result.warnings


def test_compare_periods_supports_28_day_window_and_explicit_metric() -> None:
    steps = [_obs(day, 100 + day) for day in range(56)]
    sleep = [_obs(day, 7, metric=MetricType.SLEEP_DURATION) for day in range(56)]
    result = compare_periods(
        steps + sleep, date(2026, 2, 25), window_days=28, metric=MetricType.STEPS
    )

    assert result.sample_count == 28
    assert result.baseline_sample_count == 28
    assert result.metric is MetricType.STEPS


def test_compare_periods_requires_metric_for_mixed_input() -> None:
    with pytest.raises(ValueError, match="metric is required"):
        compare_periods(
            [_obs(0, 100), _obs(0, 7, metric=MetricType.SLEEP_DURATION)],
            date(2026, 1, 1),
            window_days=1,
        )


def test_trend_uses_real_timestamp_axis() -> None:
    first = _obs(0, 1, observed_hour=8)
    second = _obs(2, 3, observed_hour=20)
    result = compute_trend([first, second], days=3)

    assert result.slope_per_day == pytest.approx(0.8)
    assert result.absolute_change == 2


def test_trend_single_point_is_stable_and_low_reliability() -> None:
    result = compute_trend([_obs(0, 10)], days=7)

    assert result.mean == 10
    assert result.slope_per_day is None
    assert "trend_requires_two_points" in result.warnings
    assert result.reliability.level is ReliabilityLevel.LOW


def test_trend_constant_two_points_has_zero_slope() -> None:
    result = compute_trend([_obs(0, 5), _obs(3, 5)], days=4)

    assert result.slope_per_day == 0
    assert result.absolute_change == 0
    assert result.relative_change == 0


def test_missingness_detects_calendar_gaps_and_explicit_missing() -> None:
    items = [
        _obs(0, 10),
        _obs(1, None, QualityFlag.MISSING),
        _obs(3, 13),
    ]
    result = summarise_missingness(items, date(2026, 1, 1), date(2026, 1, 4))

    assert result.expected_count == 4
    assert result.sample_count == 2
    assert result.explicit_missing_observations == 1
    assert result.gap_missing_observations == 1
    assert result.missing_observations == 2
    assert result.coverage == 0.5


def test_empty_missingness_summary_is_deterministic() -> None:
    result = summarise_missingness(
        [],
        date(2026, 1, 1),
        date(2026, 1, 7),
        metric=MetricType.STEPS,
    )

    assert result.sample_count == 0
    assert result.expected_count == 7
    assert result.missing_rate == 1
    assert result.reliability.level is ReliabilityLevel.LOW


def test_suspect_data_is_excluded_and_lowers_reliability() -> None:
    items = [_obs(day, 100) for day in range(7)]
    items[3] = _obs(3, 9999, QualityFlag.SUSPECT)
    result = compute_trend(items, days=7)

    assert result.sample_count == 6
    assert result.suspect_count == 1
    assert items[3].observation_id in result.source_observation_ids
    assert items[3].observation_id not in result.used_observation_ids
    assert "suspect_data" in result.reliability.reason_codes


def test_conflicting_daily_values_are_excluded_and_reported() -> None:
    items = [_obs(day, 100) for day in range(7)]
    conflict_a = _obs(3, 200)
    conflict_b = _obs(3, 300)
    items = [item for item in items if item.observed_at.date() != conflict_a.observed_at.date()]
    items.extend([conflict_a, conflict_b])
    result = compute_trend(items, days=7)

    assert result.sample_count == 6
    assert result.conflicting_count == 2
    assert conflict_a.observation_id in result.source_observation_ids
    assert conflict_a.observation_id not in result.used_observation_ids
    assert "conflicting_daily_values_excluded" in result.warnings


def test_contextual_contradiction_lowers_reliability_without_discarding_measurement() -> None:
    items = [_obs(day, 100) for day in range(7)]
    contradictory = _obs(3, 100, metadata={"contradiction_id": "synthetic-conflict"})
    items[3] = contradictory
    result = compute_trend(items, days=7)

    assert result.sample_count == 7
    assert result.conflicting_count == 1
    assert contradictory.observation_id in result.used_observation_ids
    assert "contextual_contradiction_present" in result.warnings
    assert result.reliability.level is not ReliabilityLevel.HIGH


def test_rolling_mean_enforces_policy_and_tracks_actual_window() -> None:
    items = [_obs(0, 10), _obs(1, 20), _obs(3, 40)]
    result = rolling_mean(
        items,
        window_days=3,
        minimum_observations=2,
        minimum_coverage=0.5,
    )

    assert len(result) == 4
    assert result[0].value is None
    assert result[1].value == 15
    assert result[-1].value == 30
    assert result[-1].start_date == date(2026, 1, 2)
    assert result[-1].end_date == date(2026, 1, 4)


def test_duplicate_identical_observation_is_counted_once() -> None:
    item = _obs(0, 10)
    result = summarise_missingness(
        [item, item],
        date(2026, 1, 1),
        date(2026, 1, 1),
    )

    assert result.observed_observations == 1
    assert result.sample_count == 1
    assert result.source_observation_ids == (item.observation_id,)
