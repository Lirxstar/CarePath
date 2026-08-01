from backend.domain.models import RiskLevel
from backend.safety import triage_safety


def test_tri_001_routine_sleep():
    result = triage_safety("Help me improve my sleep schedule")
    assert result.risk_level == RiskLevel.ROUTINE
    assert result.allow_normal_planning


def test_tri_002_breathing_urgent():
    result = triage_safety("I cannot breathe")
    assert result.risk_level == RiskLevel.URGENT
    assert "TRI-URG-001" in result.matched_rule_ids
    assert not result.allow_normal_planning


def test_tri_003_neurological_urgent():
    result = triage_safety("Sudden face droop and trouble speaking")
    assert result.risk_level == RiskLevel.URGENT
    assert "TRI-URG-002" in result.matched_rule_ids


def test_tri_004_serious_fall():
    result = triage_safety("I fell and lost consciousness")
    assert result.risk_level == RiskLevel.URGENT
    assert "TRI-URG-003" in result.matched_rule_ids


def test_tri_005_self_harm_plan():
    result = triage_safety("I have a suicide plan and cannot keep myself safe")
    assert result.risk_level == RiskLevel.URGENT
    assert "TRI-URG-004" in result.matched_rule_ids


def test_tri_006_recurrent_falls():
    result = triage_safety("I have repeated near-falls and my balance is getting worse")
    assert result.risk_level == RiskLevel.CAUTION
    assert "TRI-CAU-002" in result.matched_rule_ids


def test_tri_007_medication_request():
    result = triage_safety("Should I double my medication dose?")
    assert result.risk_level == RiskLevel.CAUTION
    assert "medication_request" in [flag.value for flag in result.policy_flags]
    assert result.required_response_actions


def test_tri_008_diagnosis_request():
    result = triage_safety("Do I have depression?")
    assert result.risk_level == RiskLevel.CAUTION
    assert "diagnosis_request" in [flag.value for flag in result.policy_flags]


def test_tri_009_urgent_not_downgraded():
    result = triage_safety("I cannot breathe but I think I am fine")
    assert result.risk_level == RiskLevel.URGENT


def test_tri_010_uncertain_data():
    result = triage_safety("My fall records conflict and the sensor data looks wrong")
    assert result.risk_level == RiskLevel.CAUTION
    assert "TRI-CAU-006" in result.matched_rule_ids
    assert result.uncertainty_reason


def test_multilingual_emergency_patterns():
    assert triage_safety("我无法呼吸").risk_level == RiskLevel.URGENT
    assert triage_safety("息ができない").risk_level == RiskLevel.URGENT
