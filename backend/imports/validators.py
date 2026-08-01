from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from backend.domain import Observation

REQUIRED_OBSERVATION_FIELDS = {
    "observation_id",
    "user_id",
    "metric_type",
    "value_numeric",
    "value_boolean",
    "unit",
    "observed_at",
    "source_type",
    "quality_flag",
    "confidence",
    "metadata",
}


def content_hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


def validate_observation(payload: dict[str, Any]) -> dict[str, object]:
    """Validate against CP-002 instead of duplicating metric rules."""

    observation = Observation.model_validate(payload)
    return dict(observation.model_dump(mode="python"))
