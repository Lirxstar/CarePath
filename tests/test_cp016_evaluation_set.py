from collections import Counter

from backend.evaluation.scenarios import (
    EXPECTED_CATEGORY_COUNTS,
    Language,
    ProhibitedClaim,
    SafetyOutcome,
    ScenarioCategory,
    SecurityOutcome,
    ToolName,
    load_scenario_set,
    validate_scenario_set,
    validation_errors,
)


def test_fixed_scenario_set_passes_the_cp016_contract() -> None:
    scenario_set = load_scenario_set()
    validate_scenario_set(scenario_set)

    assert len(scenario_set.scenarios) == 48
    assert Counter(scenario.category for scenario in scenario_set.scenarios) == Counter(
        EXPECTED_CATEGORY_COUNTS
    )
    assert len({scenario.scenario_id for scenario in scenario_set.scenarios}) == 48


def test_every_scenario_has_tools_evidence_safety_and_prohibited_claims() -> None:
    scenario_set = load_scenario_set()

    for scenario in scenario_set.scenarios:
        assert scenario.expected_tools
        assert scenario.expected_evidence.personal
        assert scenario.expected_evidence.external
        assert scenario.expected_findings
        assert scenario.prohibited_claims
        assert scenario.expected_response_language is scenario.language


def test_required_tools_are_all_covered() -> None:
    scenario_set = load_scenario_set()
    used_tools = {tool for scenario in scenario_set.scenarios for tool in scenario.expected_tools}
    assert used_tools == set(ToolName)


def test_safety_and_hostile_categories_have_strict_outcomes() -> None:
    scenario_set = load_scenario_set()

    safety_cases = [
        scenario
        for scenario in scenario_set.scenarios
        if scenario.category is ScenarioCategory.SAFETY_ESCALATION
    ]
    assert len(safety_cases) == 8
    assert all(
        scenario.expected_safety_outcome in {SafetyOutcome.CAUTION, SafetyOutcome.URGENT}
        for scenario in safety_cases
    )

    hostile_cases = [
        scenario
        for scenario in scenario_set.scenarios
        if scenario.category is ScenarioCategory.HOSTILE_DOCUMENT
    ]
    assert len(hostile_cases) == 4
    for scenario in hostile_cases:
        assert scenario.hostile_document
        assert scenario.expected_security_outcome is SecurityOutcome.REJECT_UNTRUSTED_INSTRUCTION
        assert ProhibitedClaim.FOLLOW_UNTRUSTED_INSTRUCTIONS in scenario.prohibited_claims


def test_multilingual_category_covers_all_frozen_languages() -> None:
    scenario_set = load_scenario_set()
    multilingual_languages = {
        scenario.language
        for scenario in scenario_set.scenarios
        if scenario.category is ScenarioCategory.MULTILINGUAL
    }
    assert multilingual_languages == {Language.EN, Language.ZH, Language.JA}


def test_validator_rejects_an_incomplete_suite() -> None:
    scenario_set = load_scenario_set()
    invalid = scenario_set.model_copy(update={"scenarios": scenario_set.scenarios[:-1]})

    errors = validation_errors(invalid)

    assert any("exactly 48" in error for error in errors)
    assert any("16/8/8/8/4/4" in error for error in errors)
