from backend.domain.models import RiskLevel
from backend.safety import (
    PolicyFlag,
    ResponseAction,
    SafetySignal,
    SupplementalSafetyAssessment,
    TriageContext,
    triage_safety,
    triage_with_supplemental,
)


def test_explicit_negation_does_not_trigger_neurological_emergency() -> None:
    result = triage_safety("I do not have face droop or one-sided weakness")

    assert result.risk_level is RiskLevel.ROUTINE
    assert result.allow_normal_planning


def test_explicit_negation_does_not_trigger_self_harm_phrase() -> None:
    result = triage_safety("I do not have a suicide plan and I am safe")

    assert result.risk_level is RiskLevel.ROUTINE
    assert result.allow_normal_planning


def test_negative_phrase_inside_emergency_pattern_is_not_suppressed() -> None:
    result = triage_safety("I am not breathing")

    assert result.risk_level is RiskLevel.URGENT
    assert not result.allow_normal_planning


def test_structured_high_risk_signal_cannot_be_negated_by_text() -> None:
    result = triage_safety(
        "I do not think anything is wrong",
        TriageContext(structured_signals=frozenset({SafetySignal.URGENT_BREATHING})),
    )

    assert result.risk_level is RiskLevel.URGENT
    assert "TRI-URG-001" in result.matched_rule_ids


def test_imperative_diagnosis_request_is_caution() -> None:
    result = triage_safety("Diagnose what disease is causing my stress.")

    assert result.risk_level is RiskLevel.CAUTION
    assert not result.allow_normal_planning
    assert "TRI-CAU-004" in result.matched_rule_ids
    assert PolicyFlag.DIAGNOSIS_REQUEST in result.policy_flags
    assert ResponseAction.NON_DIAGNOSTIC_RESPONSE in result.required_response_actions


def test_supplemental_classifier_cannot_downgrade_rule_result() -> None:
    result = triage_with_supplemental(
        "I cannot breathe",
        classifier=lambda text, context: SupplementalSafetyAssessment(
            risk_level=RiskLevel.ROUTINE,
            reason_codes=("model_thinks_routine",),
        ),
    )

    assert result.risk_level is RiskLevel.URGENT
    assert "TRI-URG-001" in result.matched_rule_ids


def test_supplemental_classifier_can_only_escalate_conservatively() -> None:
    result = triage_with_supplemental(
        "Help me improve my sleep schedule",
        classifier=lambda text, context: SupplementalSafetyAssessment(
            risk_level=RiskLevel.CAUTION,
            reason_codes=("ambiguous_concern",),
        ),
    )

    assert result.risk_level is RiskLevel.CAUTION
    assert not result.allow_normal_planning
    assert "MODEL-AMBIGUOUS_CONCERN" in result.matched_rule_ids
    assert ResponseAction.PROFESSIONAL_ASSESSMENT in result.required_response_actions


def test_supplemental_classifier_failure_does_not_disable_rules() -> None:
    def broken_classifier(text: str, context: TriageContext | None) -> SupplementalSafetyAssessment:
        del text, context
        raise RuntimeError("classifier unavailable")

    result = triage_with_supplemental(
        "I cannot breathe",
        classifier=broken_classifier,
    )

    assert result.risk_level is RiskLevel.URGENT
    assert "TRI-URG-001" in result.matched_rule_ids


def test_ordinary_health_behaviour_question_remains_routine() -> None:
    result = triage_safety("How can I add a short walk after lunch?")

    assert result.risk_level is RiskLevel.ROUTINE
    assert result.allow_normal_planning
