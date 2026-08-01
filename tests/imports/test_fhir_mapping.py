from datetime import UTC, datetime

import pytest

from backend.domain.models import AgeBand, Domain, Language, MetricType, ObservationUnit
from backend.imports.fhir.mapping import (
    age_band_from_birth_date,
    careplan_goal_reference,
    domain_code,
    goal_description,
    metric_code,
    normalize_datetime,
    normalize_reference,
    normalize_unit,
    patient_language,
    patient_timezone,
)

IMPORTED_AT = datetime(2026, 7, 28, tzinfo=UTC)


def test_age_band_mapping_covers_adult_ranges() -> None:
    assert age_band_from_birth_date("2000-08-01", IMPORTED_AT) is AgeBand.AGE_18_29
    assert age_band_from_birth_date("1990-01-01", IMPORTED_AT) is AgeBand.AGE_30_44
    assert age_band_from_birth_date("1970-01-01", IMPORTED_AT) is AgeBand.AGE_45_64
    assert age_band_from_birth_date("1950-01-01", IMPORTED_AT) is AgeBand.AGE_65_PLUS


def test_underage_patient_is_rejected() -> None:
    with pytest.raises(ValueError, match="adults only"):
        age_band_from_birth_date("2010-01-01", IMPORTED_AT)


def test_reference_normalization_handles_supported_and_invalid_forms() -> None:
    assert normalize_reference("Patient/p1") == ("Patient", "p1")
    assert normalize_reference("https://example.test/fhir/Patient/p1") == ("Patient", "p1")
    assert normalize_reference("#contained") is None
    assert normalize_reference("Patient") is None


def test_datetime_requires_timezone_and_normalizes_to_utc() -> None:
    parsed = normalize_datetime("2026-07-28T09:00:00+09:00")
    assert parsed == datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone"):
        normalize_datetime("2026-07-28T09:00:00")


def test_patient_language_and_timezone_extract_supported_values() -> None:
    patient = {
        "communication": [{"language": {"coding": [{"code": "ja-JP"}]}}],
        "extension": [{"url": "https://carepath.example/timezone", "valueString": "Asia/Tokyo"}],
    }
    assert patient_language(patient) is Language.JA
    assert patient_timezone(patient) == "Asia/Tokyo"
    assert patient_language({"communication": [{"language": {"coding": [{"code": "fr"}]}}]}) is None
    assert patient_timezone({}) is None


def test_metric_and_domain_code_preserve_unknown_coding() -> None:
    known_metric, known_metric_coding = metric_code(
        {"code": {"coding": [{"system": "carepath", "code": "steps"}]}}
    )
    unknown_metric, unknown_metric_coding = metric_code(
        {"code": {"coding": [{"system": "vendor", "code": "vendor_metric"}]}}
    )
    known_domain, known_domain_coding = domain_code(
        {"category": [{"coding": [{"system": "carepath", "code": "sleep"}]}]}
    )
    unknown_domain, unknown_domain_coding = domain_code(
        {"category": [{"coding": [{"system": "vendor", "code": "other"}]}]}
    )

    assert known_metric is MetricType.STEPS
    assert known_metric_coding["code"] == "steps"
    assert unknown_metric is None
    assert unknown_metric_coding["code"] == "vendor_metric"
    assert known_domain is Domain.SLEEP
    assert known_domain_coding["code"] == "sleep"
    assert unknown_domain is None
    assert unknown_domain_coding["code"] == "other"


def test_unit_mapping_accepts_aliases_and_rejects_unknown_unit() -> None:
    assert normalize_unit(MetricType.STEPS, {"unit": "count"}) is ObservationUnit.STEPS
    assert normalize_unit(MetricType.RESTING_HEART_RATE, {"code": "/min"}) is ObservationUnit.BPM
    assert normalize_unit(MetricType.FALL_EVENT, {}) is None
    with pytest.raises(ValueError, match="unsupported"):
        normalize_unit(MetricType.STEPS, {"unit": "kilograms"})


def test_goal_description_and_careplan_reference_require_supported_shape() -> None:
    assert goal_description({"description": {"text": "  Sleep more regularly  "}}) == (
        "Sleep more regularly"
    )
    assert careplan_goal_reference({"addresses": [{"reference": "Goal/g1"}]}) == ("Goal", "g1")
    with pytest.raises(ValueError, match="description"):
        goal_description({})
    with pytest.raises(ValueError, match="Goal"):
        careplan_goal_reference({"addresses": [{"reference": "Patient/p1"}]})
