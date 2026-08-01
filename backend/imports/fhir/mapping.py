from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.domain.models import (
    ActionStatus,
    AgeBand,
    Domain,
    GoalStatus,
    Language,
    MetricType,
    ObservationUnit,
    PlanStatus,
)

SUPPORTED_FHIR_RESOURCES = frozenset({"Patient", "Observation", "Goal", "CarePlan"})

METRIC_UNITS: dict[MetricType, ObservationUnit | None] = {
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

GOAL_STATUS_MAP: dict[str, GoalStatus] = {
    "active": GoalStatus.ACTIVE,
    "on-hold": GoalStatus.PAUSED,
    "completed": GoalStatus.COMPLETED,
    "cancelled": GoalStatus.CANCELLED,
    "entered-in-error": GoalStatus.CANCELLED,
    "rejected": GoalStatus.CANCELLED,
}

PLAN_STATUS_MAP: dict[str, PlanStatus] = {
    "draft": PlanStatus.DRAFT,
    "active": PlanStatus.ACTIVE,
    "on-hold": PlanStatus.ACTIVE,
    "completed": PlanStatus.COMPLETED,
    "revoked": PlanStatus.CANCELLED,
    "entered-in-error": PlanStatus.CANCELLED,
    "unknown": PlanStatus.DRAFT,
}

ACTION_STATUS_MAP: dict[str, ActionStatus] = {
    "not-started": ActionStatus.PROPOSED,
    "scheduled": ActionStatus.ACCEPTED,
    "in-progress": ActionStatus.ACCEPTED,
    "on-hold": ActionStatus.MODIFIED,
    "completed": ActionStatus.COMPLETED,
    "stopped": ActionStatus.NOT_COMPLETED,
    "cancelled": ActionStatus.NOT_COMPLETED,
    "unknown": ActionStatus.PROPOSED,
}


def deterministic_uuid(source_hash: str, resource_type: str, resource_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"carepath:fhir:{source_hash}:{resource_type}:{resource_id}")


def normalize_reference(reference: str | None) -> tuple[str, str] | None:
    if not reference or reference.startswith("#"):
        return None
    parts = reference.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    return parts[-2], parts[-1]


def coding(resource: dict[str, Any], field: str = "code") -> dict[str, Any]:
    container = resource.get(field)
    if not isinstance(container, dict):
        return {}
    codings = container.get("coding")
    if not isinstance(codings, list) or not codings or not isinstance(codings[0], dict):
        return {}
    return dict(codings[0])


def normalize_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("FHIR datetime is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("FHIR datetime must include timezone")
    return parsed.astimezone(UTC)


def normalize_date(value: object) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError("FHIR date is required")
    return date.fromisoformat(value[:10])


def age_band_from_birth_date(value: object, imported_at: datetime) -> AgeBand:
    birth_date = normalize_date(value)
    years = (
        imported_at.date().year
        - birth_date.year
        - ((imported_at.date().month, imported_at.date().day) < (birth_date.month, birth_date.day))
    )
    if years < 18:
        raise ValueError("CarePath simplified Patient import supports adults only")
    if years <= 29:
        return AgeBand.AGE_18_29
    if years <= 44:
        return AgeBand.AGE_30_44
    if years <= 64:
        return AgeBand.AGE_45_64
    return AgeBand.AGE_65_PLUS


def patient_language(resource: dict[str, Any]) -> Language | None:
    communications = resource.get("communication")
    if not isinstance(communications, list) or not communications:
        return None
    first = communications[0]
    if not isinstance(first, dict):
        return None
    language = first.get("language")
    if not isinstance(language, dict):
        return None
    codings = language.get("coding")
    if not isinstance(codings, list):
        return None
    for item in codings:
        if not isinstance(item, dict):
            continue
        raw_code = item.get("code")
        if not isinstance(raw_code, str):
            continue
        base = raw_code.lower().split("-")[0]
        try:
            return Language(base)
        except ValueError:
            continue
    return None


def patient_timezone(resource: dict[str, Any]) -> str | None:
    extensions = resource.get("extension")
    if not isinstance(extensions, list):
        return None
    for extension in extensions:
        if not isinstance(extension, dict):
            continue
        url = extension.get("url")
        if isinstance(url, str) and url.rstrip("/").endswith("timezone"):
            value = extension.get("valueString")
            if isinstance(value, str) and value:
                return value
    return None


def metric_code(resource: dict[str, Any]) -> tuple[MetricType | None, dict[str, Any]]:
    original = coding(resource)
    code = original.get("code")
    if not isinstance(code, str):
        return None, original
    try:
        return MetricType(code), original
    except ValueError:
        return None, original


def domain_code(resource: dict[str, Any]) -> tuple[Domain | None, dict[str, Any]]:
    category = resource.get("category")
    if not isinstance(category, list):
        return None, {}
    for item in category:
        if not isinstance(item, dict):
            continue
        codings = item.get("coding")
        if not isinstance(codings, list):
            continue
        for candidate in codings:
            if not isinstance(candidate, dict):
                continue
            code = candidate.get("code")
            if not isinstance(code, str):
                continue
            try:
                return Domain(code), dict(candidate)
            except ValueError:
                return None, dict(candidate)
    return None, {}


def normalize_unit(metric: MetricType, quantity: dict[str, Any]) -> ObservationUnit | None:
    expected = METRIC_UNITS[metric]
    if expected is None:
        return None
    raw_candidates = [quantity.get("code"), quantity.get("unit")]
    aliases: dict[ObservationUnit, set[str]] = {
        ObservationUnit.HOURS: {"h", "hr", "hour", "hours"},
        ObservationUnit.MINUTES_SINCE_MIDNIGHT: {
            "minutes_since_midnight",
            "min_since_midnight",
        },
        ObservationUnit.SCORE_1_10: {"score_1_10", "score", "1"},
        ObservationUnit.STEPS: {"steps", "{steps}", "count"},
        ObservationUnit.MINUTES: {"min", "minute", "minutes"},
        ObservationUnit.BPM: {"bpm", "beats/min", "beats/minute", "/min"},
    }
    for raw in raw_candidates:
        if isinstance(raw, str) and raw.lower() in aliases[expected]:
            return expected
    raise ValueError(f"FHIR unit for {metric.value} is unsupported: {raw_candidates}")


def goal_description(resource: dict[str, Any]) -> str:
    description = resource.get("description")
    if isinstance(description, dict):
        raw_text = description.get("text")
        if isinstance(raw_text, str):
            text = raw_text.strip()
            if text:
                return text
    raise ValueError("FHIR Goal.description.text is required")


def careplan_goal_reference(resource: dict[str, Any]) -> tuple[str, str]:
    addresses = resource.get("addresses")
    if not isinstance(addresses, list) or not addresses or not isinstance(addresses[0], dict):
        raise ValueError("FHIR CarePlan.addresses must reference a supported Goal")
    reference = normalize_reference(addresses[0].get("reference"))
    if reference is None or reference[0] != "Goal":
        raise ValueError("FHIR CarePlan.addresses must reference Goal/<id>")
    return reference
