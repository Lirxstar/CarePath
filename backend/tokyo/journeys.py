"""Frozen multilingual Tokyo journey contract for CP-202."""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.tokyo.models import TokyoResourceCategory

DEFAULT_JOURNEY_CATALOG = Path("data/tokyo/journeys.json")
_FROZEN_MVP_CATEGORIES = {
    TokyoResourceCategory.HEALTHCARE,
    TokyoResourceCategory.COOLING_SHELTER,
    TokyoResourceCategory.FAMILY_SUPPORT,
    TokyoResourceCategory.MENTAL_HEALTH_SUPPORT,
}
_REQUIRED_PRIMARY_CATEGORIES = {
    TokyoResourceCategory.HEALTHCARE,
    TokyoResourceCategory.COOLING_SHELTER,
    TokyoResourceCategory.FAMILY_SUPPORT,
}
_REQUIRED_FAILURE_IDS = {
    "location_permission_denied",
    "no_matching_resources",
    "incomplete_resource_data",
    "model_unavailable",
    "urgent_or_unsafe_request",
}


class InterfaceLanguage(StrEnum):
    EN = "en"
    JA = "ja"
    ZH = "zh"


class LocationMode(StrEnum):
    BROWSER = "browser"
    MANUAL = "manual"


class SafetyDisposition(StrEnum):
    STANDARD_NAVIGATION = "standard_navigation"
    SAFETY_CHECK_THEN_NAVIGATION = "safety_check_then_navigation"
    URGENT_ESCALATION = "urgent_escalation"


class FactOrigin(StrEnum):
    VERIFIED_DATA = "verified_data"
    DETERMINISTIC = "deterministic"
    GENERATED = "generated"


class LanguageConstraint(StrEnum):
    NONE = "none"
    REQUIRED = "required"
    PREFERRED = "preferred"


class ProductInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    natural_language_request: bool
    interface_languages: list[InterfaceLanguage]
    location_modes: list[LocationMode]
    account_required: bool
    health_upload_required: bool

    @model_validator(mode="after")
    def validate_primary_inputs(self) -> Self:
        if not self.natural_language_request:
            raise ValueError("Tokyo primary journey requires natural-language input")
        if set(self.interface_languages) != set(InterfaceLanguage):
            raise ValueError("Tokyo primary journey must support exactly EN/JA/ZH")
        if set(self.location_modes) != set(LocationMode):
            raise ValueError("Tokyo primary journey must support browser and manual location")
        if self.account_required or self.health_upload_required:
            raise ValueError("Tokyo primary journey cannot require an account or health upload")
        return self


class ProductDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    problem_statement: str
    demo_target_seconds: int = Field(gt=0, le=60)
    mvp_categories: list[TokyoResourceCategory]
    primary_inputs: ProductInputs

    @field_validator("statement", "problem_statement")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value

    @field_validator("mvp_categories")
    @classmethod
    def frozen_categories(
        cls, value: list[TokyoResourceCategory]
    ) -> list[TokyoResourceCategory]:
        if set(value) != _FROZEN_MVP_CATEGORIES or len(value) != len(_FROZEN_MVP_CATEGORIES):
            raise ValueError("CP-202 MVP categories must match the frozen four-category Tokyo scope")
        return value


class ResultCardField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    origin: FactOrigin
    required: bool
    unknown_behavior: str


class ResultAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    requires: str
    rule: str


class ResultCardContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_label: str
    generated_label: str
    fields: list[ResultCardField]
    actions: list[ResultAction]

    @model_validator(mode="after")
    def validate_grounding_boundary(self) -> Self:
        by_name = {field.name: field for field in self.fields}
        if len(by_name) != len(self.fields):
            raise ValueError("result-card field names must be unique")
        required_names = {"name", "category", "freshness", "source", "why_match"}
        if not required_names.issubset(by_name):
            raise ValueError("result-card contract is missing required fields")
        if by_name["name"].origin is not FactOrigin.VERIFIED_DATA:
            raise ValueError("resource name must be a verified source fact")
        if by_name["category"].origin is not FactOrigin.VERIFIED_DATA:
            raise ValueError("resource category must be a verified source fact")
        if by_name["source"].origin is not FactOrigin.VERIFIED_DATA:
            raise ValueError("resource source must be verified provenance")
        if by_name["freshness"].origin is not FactOrigin.DETERMINISTIC:
            raise ValueError("freshness must be derived deterministically")
        if by_name["why_match"].origin is not FactOrigin.GENERATED:
            raise ValueError("why_match must remain labelled as generated explanation")
        if "source" not in self.fact_label.lower():
            raise ValueError("verified fact label must clearly identify source facts")
        if "generated" not in self.generated_label.lower():
            raise ValueError("generated explanation label must be explicit")
        return self


class InteractionVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: InterfaceLanguage
    request: str

    @field_validator("request")
    @classmethod
    def non_empty_request(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("scenario request must not be empty")
        return value


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ManualLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    municipality: str
    labels: dict[InterfaceLanguage, str]

    @model_validator(mode="after")
    def validate_labels(self) -> Self:
        if set(self.labels) != set(InterfaceLanguage):
            raise ValueError("manual location must have EN/JA/ZH labels")
        if not self.municipality.strip() or any(not label.strip() for label in self.labels.values()):
            raise ValueError("manual location labels must not be empty")
        return self


class ScenarioLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    browser: Coordinates
    manual: ManualLocation


class ResourceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TokyoResourceCategory
    required_languages: list[str] = Field(default_factory=list)
    unknown_language_is_match: bool = False

    @field_validator("required_languages")
    @classmethod
    def normalized_languages(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("required languages must be unique")
        return normalized


class RankingExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard_constraints: list[str]
    order: list[str]
    tie_breaker: str

    @model_validator(mode="after")
    def deterministic_ranking(self) -> Self:
        if "category" not in self.hard_constraints:
            raise ValueError("category must always be a hard resource constraint")
        if not self.order or self.tie_breaker != "resource_id":
            raise ValueError("Tokyo ranking contract requires deterministic resource_id tie-breaking")
        return self


class ScenarioExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    requested_languages: list[str] = Field(default_factory=list)
    language_constraint: LanguageConstraint
    safety_disposition: SafetyDisposition
    filters: ResourceFilters
    ranking: RankingExpectation
    outcome: str

    @model_validator(mode="after")
    def validate_language_constraint(self) -> Self:
        if self.language_constraint is LanguageConstraint.REQUIRED:
            if not self.requested_languages or not self.filters.required_languages:
                raise ValueError("required language journeys need explicit requested languages")
            if self.filters.unknown_language_is_match:
                raise ValueError("unknown language support cannot satisfy a required language")
            if "required_languages" not in self.ranking.hard_constraints:
                raise ValueError("required language must remain a hard ranking constraint")
        return self


class PrimaryTokyoJourney(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    kind: str
    category: TokyoResourceCategory
    interactions: list[InteractionVariant]
    location: ScenarioLocation
    expected: ScenarioExpectation
    estimated_demo_seconds: int = Field(gt=0, le=60)
    account_required: bool
    health_upload_required: bool

    @model_validator(mode="after")
    def validate_scenario_contract(self) -> Self:
        languages = [variant.language for variant in self.interactions]
        if set(languages) != set(InterfaceLanguage) or len(languages) != len(InterfaceLanguage):
            raise ValueError("each primary Tokyo journey must contain exactly EN/JA/ZH interactions")
        if self.account_required or self.health_upload_required:
            raise ValueError("primary Tokyo journeys cannot require an account or health upload")
        if self.expected.filters.category is not self.category:
            raise ValueError("scenario category and expected filter category must match")
        if not self.scenario_id.startswith("tokyo-"):
            raise ValueError("Tokyo scenario IDs must use the tokyo- prefix")
        if not self.expected.intent.strip() or not self.expected.outcome.strip():
            raise ValueError("scenario intent and outcome must be explicit")
        return self


class FailureScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_id: str
    trigger: str
    expected_behavior: str
    safety_disposition: SafetyDisposition

    @field_validator("trigger", "expected_behavior")
    @classmethod
    def non_empty_failure_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("failure contract text must not be empty")
        return value


class TokyoJourneyCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    product: ProductDefinition
    result_card_contract: ResultCardContract
    primary_scenarios: list[PrimaryTokyoJourney]
    failure_scenarios: list[FailureScenario]

    @model_validator(mode="after")
    def validate_frozen_contract(self) -> Self:
        if self.schema_version != "cp202-v1":
            raise ValueError("unsupported Tokyo journey schema version")
        if len(self.primary_scenarios) != 3:
            raise ValueError("CP-202 freezes exactly three primary judge/demo journeys")
        scenario_ids = [scenario.scenario_id for scenario in self.primary_scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("primary Tokyo scenario IDs must be unique")
        categories = {scenario.category for scenario in self.primary_scenarios}
        if categories != _REQUIRED_PRIMARY_CATEGORIES:
            raise ValueError("primary journeys must cover healthcare, cooling shelter and family support")
        if any(
            scenario.estimated_demo_seconds > self.product.demo_target_seconds
            for scenario in self.primary_scenarios
        ):
            raise ValueError("every primary journey must fit the product demo target")
        failure_ids = [scenario.failure_id for scenario in self.failure_scenarios]
        if len(failure_ids) != len(set(failure_ids)):
            raise ValueError("failure scenario IDs must be unique")
        if set(failure_ids) != _REQUIRED_FAILURE_IDS:
            raise ValueError("CP-202 requires all five frozen failure journeys")
        urgent = next(
            scenario
            for scenario in self.failure_scenarios
            if scenario.failure_id == "urgent_or_unsafe_request"
        )
        if urgent.safety_disposition is not SafetyDisposition.URGENT_ESCALATION:
            raise ValueError("urgent/unsafe failure journey must escalate")
        return self


def load_journey_catalog(path: Path = DEFAULT_JOURNEY_CATALOG) -> TokyoJourneyCatalog:
    """Load and strictly validate the version-controlled CP-202 journey fixture."""

    return TokyoJourneyCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def iter_primary_variants(
    catalog: TokyoJourneyCatalog,
) -> Iterator[tuple[PrimaryTokyoJourney, InteractionVariant]]:
    """Yield the exact multilingual variants reused by API and browser acceptance tests."""

    for scenario in catalog.primary_scenarios:
        for interaction in scenario.interactions:
            yield scenario, interaction


def export_acceptance_cases(catalog: TokyoJourneyCatalog) -> list[dict[str, object]]:
    """Return transport-neutral acceptance cases for later CP-203/204/206 consumers."""

    cases: list[dict[str, object]] = []
    for scenario, interaction in iter_primary_variants(catalog):
        cases.append(
            {
                "case_id": f"{scenario.scenario_id}:{interaction.language.value}",
                "scenario_id": scenario.scenario_id,
                "language": interaction.language.value,
                "request": interaction.request,
                "location": scenario.location.model_dump(mode="json"),
                "expected": scenario.expected.model_dump(mode="json"),
            }
        )
    return cases


def catalog_fingerprint(catalog: TokyoJourneyCatalog) -> str:
    """Return a deterministic canonical JSON representation for fixture consumers."""

    return json.dumps(catalog.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
