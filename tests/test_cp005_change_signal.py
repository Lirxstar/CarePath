from datetime import date
from uuid import UUID

import pytest

from backend.analysis_quality import ReliabilityLevel
from backend.domain.models import MetricType, ObservationUnit
from backend.timeseries.change_signal import compute_change_signal
from backend.timeseries.models import ChangeDirection

OBSERVATION_ID = UUID("30000000-0000-0000-0000-000000000001")


def test_change_signal_detects_relative_increase_with_provenance() -> None:
    result = compute_change_signal(
        metric=MetricType.STEPS,
        unit=ObservationUnit.STEPS,
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 14),
        current_values=[120, 120, 120],
        baseline_values=[100, 100, 100],
        source_observation_ids=[OBSERVATION_ID],
        expected_count=3,
        threshold=0.15,
    )

    assert result.direction is ChangeDirection.INCREASE
    assert result.relative_change == pytest.approx(0.2)
    assert result.coverage == 1
    assert result.reliability.level is ReliabilityLevel.HIGH
    assert result.source_observation_ids == (OBSERVATION_ID,)
    assert result.used_observation_ids == (OBSERVATION_ID,)
    assert result.limitations == ("behavioural_statistical_signal_only",)


def test_change_signal_reports_stable_below_threshold() -> None:
    result = compute_change_signal(
        metric=MetricType.SLEEP_DURATION,
        unit=ObservationUnit.HOURS,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 7),
        current_values=[7.1, 7.0, 7.2],
        baseline_values=[7.0, 7.0, 7.0],
        threshold=0.1,
    )

    assert result.direction is ChangeDirection.STABLE
    assert result.absolute_change == pytest.approx(0.1)


def test_zero_baseline_does_not_invent_relative_change() -> None:
    result = compute_change_signal(
        metric=MetricType.ACTIVE_MINUTES,
        unit=ObservationUnit.MINUTES,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 7),
        current_values=[10, 10, 10],
        baseline_values=[0, 0, 0],
    )

    assert result.direction is ChangeDirection.INSUFFICIENT_DATA
    assert result.relative_change is None
    assert "baseline is zero" in result.statement


def test_empty_current_window_is_low_reliability() -> None:
    result = compute_change_signal(
        metric=MetricType.STRESS_SCORE,
        unit=ObservationUnit.SCORE_1_10,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 7),
        current_values=[],
        baseline_values=[4, 5, 4],
        expected_count=7,
    )

    assert result.direction is ChangeDirection.INSUFFICIENT_DATA
    assert result.coverage == 0
    assert result.missingness == 1
    assert result.reliability.level is ReliabilityLevel.LOW


def test_change_signal_validates_window_and_threshold() -> None:
    common = {
        "metric": MetricType.STEPS,
        "unit": ObservationUnit.STEPS,
        "current_values": [100.0],
        "baseline_values": [100.0],
    }
    with pytest.raises(ValueError, match="end_date"):
        compute_change_signal(
            **common,
            start_date=date(2026, 5, 2),
            end_date=date(2026, 5, 1),
        )
    with pytest.raises(ValueError, match="threshold"):
        compute_change_signal(
            **common,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
            threshold=-0.1,
        )
