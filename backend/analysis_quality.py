from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ReliabilityLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisReliability(BaseModel):
    """Data/statistical reliability, not medical or clinical confidence."""

    model_config = ConfigDict(frozen=True)

    level: ReliabilityLevel
    reason_codes: tuple[str, ...] = ()


def assess_reliability(
    *,
    expected_count: int,
    valid_count: int,
    suspect_count: int = 0,
    conflicting_count: int = 0,
    minimum_samples: int = 3,
    baseline_available: bool = True,
) -> AnalysisReliability:
    """Apply one deterministic reliability vocabulary across CP-005 analytics."""
    if expected_count < 0 or valid_count < 0:
        raise ValueError("counts must be non-negative")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")

    reasons: list[str] = []
    coverage = min(1.0, valid_count / expected_count) if expected_count else 0.0

    if valid_count == 0:
        reasons.append("no_valid_data")
    elif valid_count < 2:
        reasons.append("insufficient_samples")
    elif valid_count < minimum_samples:
        reasons.append("small_sample")

    if expected_count:
        if coverage < 0.5:
            reasons.append("very_low_coverage")
        elif coverage < 0.8:
            reasons.append("incomplete_coverage")
    if suspect_count:
        reasons.append("suspect_data")
    if conflicting_count:
        reasons.append("conflicting_data")
    if not baseline_available:
        reasons.append("baseline_unavailable")

    conflict_ratio = conflicting_count / max(1, valid_count + conflicting_count)
    low_reasons = {
        "no_valid_data",
        "insufficient_samples",
        "very_low_coverage",
        "baseline_unavailable",
    }
    if low_reasons.intersection(reasons) or conflict_ratio >= 0.2:
        level = ReliabilityLevel.LOW
    elif reasons:
        level = ReliabilityLevel.MEDIUM
    else:
        level = ReliabilityLevel.HIGH

    return AnalysisReliability(level=level, reason_codes=tuple(reasons))
