from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import backend.tokyo.safety as tokyo_safety
from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.tokyo.journeys import InterfaceLanguage
from backend.tokyo.safety import (
    TokyoSafetyAvailabilityState,
    TokyoSafetyDisposition,
    TokyoSafetyEligibilityState,
    TokyoSafetyReference,
    TokyoSafetyVerificationStatus,
    assess_tokyo_safety,
)


_AS_OF = date(2026, 8, 13)


def _replace_reference(
    reference: TokyoSafetyReference,
    **updates: object,
) -> TokyoSafetyReference:
    payload = reference.model_dump()
    payload.update(updates)
    return TokyoSafetyReference.model_validate(payload)


def test_expired_preferred_reference_is_not_actionable_and_119_remains_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired_7119 = _replace_reference(
        tokyo_safety.EMERGENCY_CONSULTATION_7119_REFERENCE,
        valid_until=date(2026, 8, 12),
    )
    monkeypatch.setattr(
        tokyo_safety,
        "EMERGENCY_CONSULTATION_7119_REFERENCE",
        expired_7119,
    )

    decision = assess_tokyo_safety(
        "Should I stop my medication dose?",
        InterfaceLanguage.EN,
        as_of=_AS_OF,
    )
    references = {reference.source_id: reference for reference in decision.references}

    assert decision.disposition is TokyoSafetyDisposition.URGENT_PROFESSIONAL_HELP
    assert decision.bypass_resource_navigation is True
    assert references["tokyo-fire-emergency-consultation-7119"].verification_status is (
        TokyoSafetyVerificationStatus.EXPIRED
    )
    assert (
        references["tokyo-fire-emergency-consultation-7119"].currently_verified_actionable is False
    )
    assert references["tokyo-health-ambulance-119"].verification_status is (
        TokyoSafetyVerificationStatus.VERIFIED_CURRENT
    )
    assert "#7119" not in decision.message
    assert "call 119" in decision.message


def test_unknown_emergency_reference_never_downgrades_emergency_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown_119 = _replace_reference(
        tokyo_safety.AMBULANCE_119_REFERENCE,
        availability_state=TokyoSafetyAvailabilityState.UNKNOWN,
    )
    monkeypatch.setattr(tokyo_safety, "AMBULANCE_119_REFERENCE", unknown_119)

    decision = assess_tokyo_safety(
        "I can't breathe. Find me a nearby clinic.",
        InterfaceLanguage.EN,
        as_of=_AS_OF,
    )
    ambulance = next(
        reference
        for reference in decision.references
        if reference.source_id == "tokyo-health-ambulance-119"
    )

    assert decision.disposition is TokyoSafetyDisposition.EMERGENCY_ESCALATION
    assert decision.bypass_resource_navigation is True
    assert ambulance.verification_status is TokyoSafetyVerificationStatus.AVAILABILITY_UNKNOWN
    assert ambulance.currently_verified_actionable is False
    assert "call 119" not in decision.message
    assert "current official source" in decision.message


def test_inapplicable_preferred_route_is_suppressed_without_lowering_safety(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inapplicable_7119 = _replace_reference(
        tokyo_safety.EMERGENCY_CONSULTATION_7119_REFERENCE,
        eligibility="fixture-ineligible",
        eligibility_state=TokyoSafetyEligibilityState.VERIFIED_INAPPLICABLE,
    )
    monkeypatch.setattr(
        tokyo_safety,
        "EMERGENCY_CONSULTATION_7119_REFERENCE",
        inapplicable_7119,
    )

    decision = assess_tokyo_safety(
        "Do I have heart disease and should I stop my medication?",
        InterfaceLanguage.EN,
        as_of=_AS_OF,
    )
    references = {reference.source_id: reference for reference in decision.references}

    assert decision.disposition is TokyoSafetyDisposition.URGENT_PROFESSIONAL_HELP
    assert decision.bypass_resource_navigation is True
    assert references["tokyo-fire-emergency-consultation-7119"].verification_status is (
        TokyoSafetyVerificationStatus.VERIFIED_INAPPLICABLE
    )
    assert "#7119" not in decision.message
    assert "call 119" in decision.message


def test_unknown_language_support_is_not_inferred_from_interface_language() -> None:
    decision = assess_tokyo_safety(
        "我不确定这是不是紧急情况。",
        InterfaceLanguage.ZH,
        as_of=_AS_OF,
    )

    assert decision.references
    assert all(reference.languages is None for reference in decision.references)


def test_superseded_reference_is_quarantined_and_escalation_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    superseded_7119 = _replace_reference(
        tokyo_safety.EMERGENCY_CONSULTATION_7119_REFERENCE,
        superseded_by_source_id="tokyo-fire-newer-consultation-reference",
    )
    monkeypatch.setattr(
        tokyo_safety,
        "EMERGENCY_CONSULTATION_7119_REFERENCE",
        superseded_7119,
    )

    decision = assess_tokyo_safety(
        "Should I change my medication dose?",
        InterfaceLanguage.EN,
        as_of=_AS_OF,
    )
    references = {reference.source_id: reference for reference in decision.references}

    assert decision.disposition is TokyoSafetyDisposition.URGENT_PROFESSIONAL_HELP
    assert references["tokyo-fire-emergency-consultation-7119"].verification_status is (
        TokyoSafetyVerificationStatus.SUPERSEDED
    )
    assert "#7119" not in decision.message
    assert "call 119" in decision.message


def test_unknown_eligibility_fails_closed_for_action_driving_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown_eligibility = _replace_reference(
        tokyo_safety.EMERGENCY_CONSULTATION_7119_REFERENCE,
        eligibility_state=TokyoSafetyEligibilityState.UNKNOWN,
    )
    monkeypatch.setattr(
        tokyo_safety,
        "EMERGENCY_CONSULTATION_7119_REFERENCE",
        unknown_eligibility,
    )

    decision = assess_tokyo_safety(
        "I feel very unwell and don't know if this is serious.",
        InterfaceLanguage.EN,
        as_of=_AS_OF,
    )
    consultation = next(
        reference
        for reference in decision.references
        if reference.source_id == "tokyo-fire-emergency-consultation-7119"
    )

    assert decision.disposition is TokyoSafetyDisposition.INSUFFICIENT_INFORMATION
    assert consultation.verification_status is TokyoSafetyVerificationStatus.ELIGIBILITY_UNKNOWN
    assert consultation.currently_verified_actionable is False
    assert "#7119" not in decision.message
    assert "call 119" in decision.message


def test_safety_api_serializes_freshness_availability_and_actionability() -> None:
    app = create_app(settings=Settings(environment="test", llm_provider="mock"))

    with TestClient(app) as client:
        response = client.post(
            "/tokyo/safety/triage",
            json={
                "query": "Should I stop my medication dose?",
                "interface_language": "en",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["references"]
    for reference in payload["references"]:
        assert reference["retrieved_at"]
        assert reference["valid_until"]
        assert reference["availability_state"] in {
            "verified_available",
            "unknown",
            "verified_unavailable",
        }
        assert reference["eligibility_state"] in {
            "verified_applicable",
            "unknown",
            "verified_inapplicable",
        }
        assert reference["verification_status"] != "unevaluated"
        assert isinstance(reference["currently_verified_actionable"], bool)
        assert "languages" in reference
