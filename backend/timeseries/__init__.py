"""Deterministic longitudinal health behaviour analytics."""

from .analysis import compare_periods, compute_trend, rolling_mean, summarise_missingness
from .change_signal import compute_change_signal
from .models import (
    ChangeDirection,
    ChangeSignal,
    MissingnessSummary,
    PeriodComparisonResult,
    RollingMeanPoint,
    TimeSeriesBaseResult,
    TrendResult,
)

__all__ = [
    "ChangeDirection",
    "ChangeSignal",
    "MissingnessSummary",
    "PeriodComparisonResult",
    "RollingMeanPoint",
    "TimeSeriesBaseResult",
    "TrendResult",
    "compare_periods",
    "compute_change_signal",
    "compute_trend",
    "rolling_mean",
    "summarise_missingness",
]
