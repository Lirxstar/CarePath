from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.tokyo.journeys import (
    FactOrigin,
    InterfaceLanguage,
    LanguageConstraint,
    SafetyDisposition,
    TokyoJourneyCatalog,
    catalog_fingerprint,
    export_acceptance_cases,
    load_journey_catalog,
)

FIXTURE = Path("data/tokyo/journeys.json")


def _raw_catalog() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_frozen_catalog_has_three_multilingual_primary_journeys() -> None:
    catalog = load_journey_catalog()
    assert catalog.schema_version == "cp202-v1"
    assert len(catalog.primary_scenarios) == 3
    assert catalog.product.demo_target_seconds == 60
    assert catalog.product.primary_inputs.account_required is False
    assert catalog.product.primary_inputs.health_upload_required is False
    for scenario in catalog.primary_scenarios:
        assert {variant.language for variant in scenario.interactions} == set(InterfaceLanguage)
        assert scenario.estimated_demo_seconds <= 60
        assert scenario.account_required is False
        assert scenario.health_upload_required is False


def test_primary_journeys_freeze_intent_filters_ranking_and_safety() -> None:
    catalog = load_journey_catalog()
    by_id = {scenario.scenario_id: scenario for scenario in catalog.primary_scenarios}

    healthcare = by_id["tokyo-healthcare-language"]
    assert healthcare.expected.intent == "find_healthcare"
    assert healthcare.expected.language_constraint is LanguageConstraint.REQUIRED
    assert healthcare.expected.filters.required_languages == ["en"]
    assert healthcare.expected.filters.unknown_language_is_match is False
    assert "required_languages" in healthcare.expected.ranking.hard_constraints

    heat = by_id["tokyo-heat-cooling-shelter"]
    assert heat.expected.intent == "find_cooling_shelter"
    assert heat.expected.safety_disposition is SafetyDisposition.SAFETY_CHECK_THEN_NAVIGATION

    family = by_id["tokyo-family-support-unknown-service"]
    assert family.expected.intent == "find_family_support"
    assert family.expected.safety_disposition is SafetyDisposition.STANDARD_NAVIGATION

    for scenario in catalog.primary_scenarios:
        assert scenario.expected.ranking.tie_breaker == "resource_id"
        assert scenario.expected.ranking.order[-1] == "stable_id"


def test_result_card_contract_distinguishes_verified_facts_from_generation() -> None:
    catalog = load_journey_catalog()
    fields = {field.name: field for field in catalog.result_card_contract.fields}
    assert fields["name"].origin is FactOrigin.VERIFIED_DATA
    assert fields["source"].origin is FactOrigin.VERIFIED_DATA
    assert fields["distance_km"].origin is FactOrigin.DETERMINISTIC
    assert fields["why_match"].origin is FactOrigin.GENERATED
    languages = fields["languages"]
    assert "never_infer" in languages.unknown_behavior
    actions = {action.action: action.requires for action in catalog.result_card_contract.actions}
    assert actions == {
        "directions": "verified_location",
        "call": "source_phone",
        "official_source": "provenance_url",
    }


def test_failure_contract_covers_location_empty_incomplete_model_and_safety() -> None:
    catalog = load_journey_catalog()
    failures = {scenario.failure_id: scenario for scenario in catalog.failure_scenarios}
    assert set(failures) == {
        "location_permission_denied",
        "no_matching_resources",
        "incomplete_resource_data",
        "model_unavailable",
        "urgent_or_unsafe_request",
    }
    assert "manual" in failures["location_permission_denied"].expected_behavior.lower()
    assert "never invent" in failures["no_matching_resources"].expected_behavior.lower()
    assert "unknown" in failures["incomplete_resource_data"].expected_behavior.lower()
    assert "deterministic" in failures["model_unavailable"].expected_behavior.lower()
    assert (
        failures["urgent_or_unsafe_request"].safety_disposition
        is SafetyDisposition.URGENT_ESCALATION
    )


def test_same_fixture_exports_nine_transport_neutral_acceptance_cases() -> None:
    catalog = load_journey_catalog()
    cases = export_acceptance_cases(catalog)
    assert len(cases) == 9
    assert len({case["case_id"] for case in cases}) == 9
    assert {case["language"] for case in cases} == {"en", "ja", "zh"}
    for case in cases:
        assert case["request"]
        assert case["location"]
        assert case["expected"]
    assert catalog_fingerprint(catalog) == catalog_fingerprint(load_journey_catalog())


def test_catalog_rejects_silent_language_constraint_weakening() -> None:
    raw = _raw_catalog()
    primary = raw["primary_scenarios"]
    assert isinstance(primary, list)
    healthcare = primary[0]
    assert isinstance(healthcare, dict)
    expected = healthcare["expected"]
    assert isinstance(expected, dict)
    filters = expected["filters"]
    assert isinstance(filters, dict)
    filters["unknown_language_is_match"] = True
    with pytest.raises(ValidationError, match="unknown language support"):
        TokyoJourneyCatalog.model_validate(raw)


def test_catalog_rejects_missing_language_variant_or_health_upload_requirement() -> None:
    raw = _raw_catalog()
    primary = raw["primary_scenarios"]
    assert isinstance(primary, list)
    heat = primary[1]
    assert isinstance(heat, dict)
    interactions = heat["interactions"]
    assert isinstance(interactions, list)
    heat["interactions"] = interactions[:2]
    with pytest.raises(ValidationError, match="exactly EN/JA/ZH"):
        TokyoJourneyCatalog.model_validate(raw)

    raw = _raw_catalog()
    primary = raw["primary_scenarios"]
    assert isinstance(primary, list)
    family = primary[2]
    assert isinstance(family, dict)
    family["health_upload_required"] = True
    with pytest.raises(ValidationError, match="cannot require an account or health upload"):
        TokyoJourneyCatalog.model_validate(raw)
