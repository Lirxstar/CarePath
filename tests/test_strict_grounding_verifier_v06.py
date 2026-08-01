from backend.agents import EvidenceRef, WorkflowState
from backend.domain.models import RiskLevel
from backend.safety import StrictGroundingSafetyVerifier, VerificationStatus


def _state() -> WorkflowState:
    return WorkflowState(
        interaction_id="strict-verifier-1",
        user_id="user-a",
        request_text="Help with my sleep routine",
        risk_level=RiskLevel.ROUTINE,
        external_evidence=[
            EvidenceRef(
                evidence_id="external:activity",
                content=(
                    "Adults can use regular walking and movement breaks to support "
                    "physical activity."
                ),
                source_id="src-activity",
            )
        ],
    )


def test_known_but_wrong_domain_citation_is_rejected() -> None:
    state = _state()
    state.draft = {
        "claims": [
            {
                "claim_id": "wrong-citation",
                "kind": "general_health",
                "statement": "Keep a regular sleep schedule to support healthy sleep habits.",
                "evidence_ids": ["external:activity"],
            }
        ]
    }

    result = StrictGroundingSafetyVerifier().verify(state)

    assert result.status is VerificationStatus.REGENERATE_ONCE
    assert "VER-GROUND-005" in result.failed_rule_ids
    audit = state.context["audit_trace"]
    assert audit[-1]["output_summary"]["verification_passed"] is False
    assert "VER-GROUND-005" in audit[-1]["output_summary"]["failed_rule_ids"]


def test_sanitizer_flag_is_preserved_in_verifier_audit_without_raw_payload() -> None:
    state = _state()
    state.external_evidence[0] = EvidenceRef(
        evidence_id="external:sleep",
        content="A regular sleep schedule can support healthy sleep habits.",
        source_id="src-sleep",
    )
    state.context["prompt_injection_detected"] = True
    state.draft = {
        "claims": [
            {
                "claim_id": "sleep-guidance",
                "kind": "general_health",
                "statement": "A regular sleep schedule can support healthy sleep habits.",
                "evidence_ids": ["external:sleep"],
            }
        ]
    }

    result = StrictGroundingSafetyVerifier().verify(state)

    assert result.status is VerificationStatus.PASS
    assert result.prompt_injection_detected is True
    audit = state.context["audit_trace"]
    assert audit[-1]["output_summary"]["prompt_injection_detected"] is True
    assert "ignore previous instructions" not in str(audit).lower()
