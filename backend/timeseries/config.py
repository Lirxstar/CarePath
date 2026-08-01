from __future__ import annotations

from backend.domain.models import MetricType, ObservationUnit

# CP-005 uses one expected daily slot for each frozen longitudinal metric.
# This is an analytics coverage policy, not a clinical sampling recommendation.
EXPECTED_OBSERVATIONS_PER_DAY: dict[MetricType, int] = dict.fromkeys(MetricType, 1)

UNIT_BY_METRIC: dict[MetricType, ObservationUnit | None] = {
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


def expected_count(metric: MetricType, days: int) -> int:
    if days < 0:
        raise ValueError("days must be non-negative")
    return EXPECTED_OBSERVATIONS_PER_DAY[metric] * days
