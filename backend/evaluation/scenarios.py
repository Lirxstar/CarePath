from __future__ import annotations

import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class ScenarioCategory(StrEnum):
    ROUTINE_COACHING = "routine_coaching"
    LONGITUDINAL_TREND = "longitudinal_trend"
    MISSING_OR_CONFLICTING_DATA = "missing_or_conflicting_data"
    SAFETY_ESCALATION = "safety_escalation"
    HOSTILE_DOCUMENT = "hostile_document"
    MULTILINGUAL = "multilingual"


class Language(StrEnum):
    EN = "en"
    ZH = "zh"
    JA = "ja"


class SafetyOutcome(StrEnum):
    ROUTINE = "routine"
    CAUTION = "caution"
    URGENT = "urgent"


class SecurityOutcome(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    REJECT_UNTRUSTED_INSTRUCTION = "reject_untrusted_instruction"


class ToolName(StrEnum):
    COMPARE_PERIODS = "compare_periods"
    COMPUTE_TREND = "compute_trend"
    SUMMARISE_MISSINGNESS = "summarise_missingness"
    SUMMARISE_ADHERENCE = "summarise_adherence"
    RETRIEVE_PERSONAL_CONTEXT = "retrieve_personal_context"
    RETRIEVE_EXTERNAL_EVIDENCE = "retrieve_external_evidence"


class ProhibitedClaim(StrEnum):
    DIAGNOSIS = "diagnosis"
    MEDICATION_CHANGE = "medication_change"
    CAUSAL_MEDICAL_INFERENCE = "causal_medical_inference"
    FABRICATE_EVIDENCE = "fabricate_evidence"
    IGNORE_MISSINGNESS = "ignore_missingness"
    IGNORE_CONFLICTING_DATA = "ignore_conflicting_data"
    IGNORE_QUALITY_FLAGS = "ignore_quality_flags"
    OVERSTATE_CERTAINTY = "overstate_certainty"
    DISCOURAGE_PROFESSIONAL_HELP = "discourage_professional_help"
    DELAY_URGENT_CARE = "delay_urgent_care"
    FOLLOW_UNTRUSTED_INSTRUCTIONS = "follow_untrusted_instructions"
    DISCLOSE_SYSTEM_PROMPT = "disclose_system_prompt"
    DISCLOSE_PRIVATE_DATA = "disclose_private_data"
    CLAIM_CLINICAL_VALIDATION = "claim_clinical_validation"
    GUARANTEE_OUTCOME = "guarantee_outcome"
    CONTRADICT_USER_REPORT = "contradict_user_report"
    UNSAFE_ACTIVITY_ESCALATION = "unsafe_activity_escalation"
    IGNORE_USER_PREFERENCE = "ignore_user_preference"
    IGNORE_ADHERENCE_HISTORY = "ignore_adherence_history"


class EvidenceExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    personal: tuple[str, ...] = Field(min_length=1)
    external: tuple[str, ...] = Field(min_length=1)


class EvaluationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^CP016-(RT|TR|MC|SF|HI|ML)-\d{3}$")
    category: ScenarioCategory
    title: str = Field(min_length=1)
    persona_id: str = Field(min_length=1)
    language: Language
    expected_response_language: Language
    user_question: str = Field(min_length=1)
    context_overrides: tuple[str, ...] = Field(min_length=1)
    expected_tools: tuple[ToolName, ...] = Field(min_length=1)
    expected_evidence: EvidenceExpectation
    expected_findings: tuple[str, ...] = Field(min_length=1)
    expected_safety_outcome: SafetyOutcome
    expected_security_outcome: SecurityOutcome
    prohibited_claims: tuple[ProhibitedClaim, ...] = Field(min_length=1)
    hostile_document: str | None = None


class ScenarioSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite_id: str
    description: str
    category_counts: dict[ScenarioCategory, int]
    scenarios: tuple[EvaluationScenario, ...]


class ScenarioSetValidationError(ValueError):
    """Raised when the fixed scenario set violates the CP-016 contract."""


EXPECTED_CATEGORY_COUNTS: Final[dict[ScenarioCategory, int]] = {
    ScenarioCategory.ROUTINE_COACHING: 16,
    ScenarioCategory.LONGITUDINAL_TREND: 8,
    ScenarioCategory.MISSING_OR_CONFLICTING_DATA: 8,
    ScenarioCategory.SAFETY_ESCALATION: 8,
    ScenarioCategory.HOSTILE_DOCUMENT: 4,
    ScenarioCategory.MULTILINGUAL: 4,
}
EXPECTED_LANGUAGES: Final[set[Language]] = {Language.EN, Language.ZH, Language.JA}
EXPECTED_TOOLS: Final[set[ToolName]] = set(ToolName)
PERSONAL_EVIDENCE_PREFIXES: Final[tuple[str, ...]] = (
    "observation:",
    "journal:",
    "feedback:",
    "profile:",
    "plan:",
    "event:",
    "quality_flag:",
)
EXTERNAL_EVIDENCE_PREFIXES: Final[tuple[str, ...]] = (
    "topic:",
    "source:",
    "untrusted_document:",
)
DEFAULT_SCENARIO_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "evaluation" / "scenarios.json"
)


def load_scenario_set(path: Path | None = None) -> ScenarioSet:
    target = path or DEFAULT_SCENARIO_PATH
    return ScenarioSet.model_validate_json(target.read_text(encoding="utf-8"))


def validation_errors(scenario_set: ScenarioSet) -> tuple[str, ...]:
    errors: list[str] = []

    if scenario_set.schema_version != "1.0":
        errors.append("schema_version must be 1.0")
    if scenario_set.suite_id != "carepath-cp016-v1":
        errors.append("suite_id must be carepath-cp016-v1")
    if len(scenario_set.scenarios) != 48:
        errors.append(f"expected exactly 48 scenarios, found {len(scenario_set.scenarios)}")

    identifiers = [scenario.scenario_id for scenario in scenario_set.scenarios]
    if len(identifiers) != len(set(identifiers)):
        errors.append("scenario_id values must be unique")

    declared_counts = dict(scenario_set.category_counts)
    if declared_counts != EXPECTED_CATEGORY_COUNTS:
        errors.append("declared category_counts do not match the CP-016 contract")

    actual_counts: Counter[ScenarioCategory] = Counter(
        scenario.category for scenario in scenario_set.scenarios
    )
    if dict(actual_counts) != EXPECTED_CATEGORY_COUNTS:
        errors.append(
            "actual category counts do not match the required 16/8/8/8/4/4 distribution"
        )

    used_tools: set[ToolName] = set()
    multilingual_languages: set[Language] = set()

    for scenario in scenario_set.scenarios:
        if scenario.expected_response_language != scenario.language:
            errors.append(
                f"{scenario.scenario_id}: expected response language must match scenario language"
            )

        if len(scenario.expected_tools) != len(set(scenario.expected_tools)):
            errors.append(f"{scenario.scenario_id}: expected_tools contains duplicates")
        used_tools.update(scenario.expected_tools)

        if not all(
            ref.startswith(PERSONAL_EVIDENCE_PREFIXES)
            for ref in scenario.expected_evidence.personal
        ):
            errors.append(f"{scenario.scenario_id}: invalid personal evidence reference")
        if not all(
            ref.startswith(EXTERNAL_EVIDENCE_PREFIXES)
            for ref in scenario.expected_evidence.external
        ):
            errors.append(f"{scenario.scenario_id}: invalid external evidence reference")

        if scenario.category is ScenarioCategory.SAFETY_ESCALATION:
            if scenario.expected_safety_outcome is SafetyOutcome.ROUTINE:
                errors.append(
                    f"{scenario.scenario_id}: safety scenarios must escalate to caution or urgent"
                )
        if scenario.category is ScenarioCategory.HOSTILE_DOCUMENT:
            if not scenario.hostile_document:
                errors.append(f"{scenario.scenario_id}: hostile_document is required")
            if (
                scenario.expected_security_outcome
                is not SecurityOutcome.REJECT_UNTRUSTED_INSTRUCTION
            ):
                errors.append(
                    f"{scenario.scenario_id}: hostile scenarios must reject the instruction"
                )
            if (
                ProhibitedClaim.FOLLOW_UNTRUSTED_INSTRUCTIONS
                not in scenario.prohibited_claims
            ):
                errors.append(
                    f"{scenario.scenario_id}: hostile scenarios must prohibit following "
                    "untrusted instructions"
                )
            if not any(
                ref.startswith("untrusted_document:")
                for ref in scenario.expected_evidence.external
            ):
                errors.append(
                    f"{scenario.scenario_id}: hostile scenarios need an untrusted-document ref"
                )
        else:
            if scenario.hostile_document is not None:
                errors.append(
                    f"{scenario.scenario_id}: hostile_document is only valid for hostile scenarios"
                )
            if scenario.expected_security_outcome is not SecurityOutcome.NOT_APPLICABLE:
                errors.append(
                    f"{scenario.scenario_id}: non-hostile scenarios use not_applicable security"
                )

        if scenario.category is ScenarioCategory.MULTILINGUAL:
            multilingual_languages.add(scenario.language)

    if used_tools != EXPECTED_TOOLS:
        missing = sorted(tool.value for tool in EXPECTED_TOOLS - used_tools)
        errors.append(f"the fixed set must cover all required tools; missing={missing}")

    if multilingual_languages != EXPECTED_LANGUAGES:
        present = sorted(language.value for language in multilingual_languages)
        errors.append(
            "multilingual scenarios must cover English, Chinese, and Japanese; "
            f"present={present}"
        )

    return tuple(errors)


def validate_scenario_set(scenario_set: ScenarioSet) -> None:
    errors = validation_errors(scenario_set)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise ScenarioSetValidationError(f"CP-016 scenario validation failed:\n{details}")


def summary(scenario_set: ScenarioSet) -> dict[str, object]:
    return {
        "suite_id": scenario_set.suite_id,
        "schema_version": scenario_set.schema_version,
        "scenario_count": len(scenario_set.scenarios),
        "category_counts": {
            category.value: count
            for category, count in sorted(
                Counter(
                    scenario.category for scenario in scenario_set.scenarios
                ).items(),
                key=lambda item: item[0].value,
            )
        },
        "languages": sorted({scenario.language.value for scenario in scenario_set.scenarios}),
        "tools": sorted(
            {
                tool.value
                for scenario in scenario_set.scenarios
                for tool in scenario.expected_tools
            }
        ),
    }


def main() -> int:
    scenario_set = load_scenario_set()
    validate_scenario_set(scenario_set)
    print(json.dumps(summary(scenario_set), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
