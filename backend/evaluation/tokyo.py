"""Deterministic CP-207 engineering evaluation for CarePath Tokyo.

The suite executes the public Tokyo agent API against a fixed source-backed resource
fixture and a deliberately unavailable model provider. This keeps CI credential-free
while exercising CP-205 safety, CP-204 fallback, CP-203 search/ranking and CP-201
provenance through the real HTTP contract. It is a software-engineering evaluation,
not clinical validation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.api.app.config import Settings
from backend.api.app.llm.provider import JsonObject, LLMProvider
from backend.api.app.main import create_app
from backend.tokyo.journeys import InterfaceLanguage
from backend.tokyo.models import Freshness, SourceProvenance, TokyoResource, TokyoResourceCategory
from backend.tokyo.safety import TokyoSafetyDisposition, assess_tokyo_safety
from backend.tokyo.search import TokyoResourceRepository

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_PATH = _REPOSITORY_ROOT / "evaluation" / "tokyo" / "scenarios.json"


class TokyoEvaluationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    primary_completion_percent: float = Field(ge=0, le=100)
    intent_tool_selection_percent: float = Field(ge=0, le=100)
    geo_ranking_percent: float = Field(ge=0, le=100)
    safety_escalation_recall_percent: float = Field(ge=0, le=100)
    unsupported_factual_resource_claims_max: int = Field(ge=0)
    provenance_presence_percent: float = Field(ge=0, le=100)
    language_fidelity_percent: float = Field(ge=0, le=100)


class TokyoEvaluationLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["coordinates", "municipality"]
    latitude: float | None = None
    longitude: float | None = None
    municipality: str | None = None

    def api_payload(self) -> dict[str, object]:
        payload = self.model_dump(exclude_none=True)
        return {key: value for key, value in payload.items()}


class TokyoEvaluationFreshnessExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: dict[str, Freshness]


class TokyoEvaluationExpected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    intent: str | None
    category: str | None
    ordered_resource_ids: list[str] | None = None
    safety_disposition: TokyoSafetyDisposition
    null_fields: list[str] = Field(default_factory=list)
    freshness: dict[str, Freshness] = Field(default_factory=dict)
    explanation_model_status: str | None = None
    message_contains: str | None = None


class TokyoEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    tags: list[str]
    language: InterfaceLanguage
    query: str
    location: TokyoEvaluationLocation
    expected: TokyoEvaluationExpected

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("evaluation tags must be non-empty and unique")
        return value


class TokyoEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["cp207-v1"]
    description: str
    thresholds: TokyoEvaluationThresholds
    cases: list[TokyoEvaluationCase] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def unique_case_ids(cls, value: list[TokyoEvaluationCase]) -> list[TokyoEvaluationCase]:
        ids = [case.case_id for case in value]
        if len(ids) != len(set(ids)):
            raise ValueError("CP-207 evaluation case IDs must be unique")
        return value


class TokyoEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    tags: list[str]
    status: str
    passed: bool
    intent_tool_ok: bool
    ranking_ok: bool
    safety_ok: bool
    grounding_ok: bool
    provenance_ok: bool
    language_ok: bool
    unsupported_factual_resource_claims: int
    returned_resource_ids: list[str]
    failures: list[str]


class TokyoEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_cases: int
    passed_cases: int
    primary_completion_percent: float
    intent_tool_selection_percent: float
    geo_ranking_percent: float
    safety_escalation_recall_percent: float
    grounded_resource_claim_precision_percent: float
    unsupported_factual_resource_claims: int
    provenance_presence_percent: float
    language_fidelity_percent: float


class TokyoEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["cp207-report-v1"] = "cp207-report-v1"
    evaluation_kind: Literal["software_engineering_acceptance"] = "software_engineering_acceptance"
    clinical_effectiveness_claimed: Literal[False] = False
    scenario_sha256: str
    provider_mode: Literal["forced_unavailable"] = "forced_unavailable"
    fixture_resource_count: int
    metrics: TokyoEvaluationMetrics
    thresholds: TokyoEvaluationThresholds
    threshold_pass: bool
    cases: list[TokyoEvaluationCaseResult]


class UnavailableEvaluationProvider(LLMProvider):
    """Credential-free provider used to exercise the product fallback path."""

    @property
    def is_local(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        raise RuntimeError("CP-207 intentionally disables model generation")

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        del prompt, schema, kwargs
        raise RuntimeError("CP-207 intentionally disables structured model generation")

    async def health_check(self) -> JsonObject:
        return {"status": "unavailable", "provider": "cp207-forced-unavailable"}


def load_tokyo_evaluation_suite(path: Path = DEFAULT_SCENARIO_PATH) -> TokyoEvaluationSuite:
    return TokyoEvaluationSuite.model_validate_json(path.read_text(encoding="utf-8"))


def build_tokyo_evaluation_repository() -> TokyoResourceRepository:
    return TokyoResourceRepository(
        [
            _resource(
                "clinic-en-near",
                TokyoResourceCategory.HEALTHCARE,
                latitude=35.6938,
                longitude=139.7034,
                municipality="新宿区",
                languages=["en"],
                phone="03-1000-0001",
            ),
            _resource(
                "clinic-en-far",
                TokyoResourceCategory.HEALTHCARE,
                latitude=35.7038,
                longitude=139.7034,
                municipality="新宿区",
                languages=["en"],
            ),
            _resource(
                "clinic-unknown-language",
                TokyoResourceCategory.HEALTHCARE,
                latitude=35.6939,
                longitude=139.7034,
                municipality="新宿区",
                languages=[],
            ),
            _resource(
                "cooling-koto-near",
                TokyoResourceCategory.COOLING_SHELTER,
                latitude=35.6729,
                longitude=139.8174,
                municipality="江東区",
            ),
            _resource(
                "cooling-koto-far",
                TokyoResourceCategory.COOLING_SHELTER,
                latitude=35.6829,
                longitude=139.8174,
                municipality="江東区",
            ),
            _resource(
                "family-koto-partial",
                TokyoResourceCategory.FAMILY_SUPPORT,
                latitude=35.6729,
                longitude=139.8174,
                municipality="江東区",
                opening_hours=None,
                phone=None,
            ),
            _resource(
                "mental-stale-near",
                TokyoResourceCategory.MENTAL_HEALTH_SUPPORT,
                latitude=35.6938,
                longitude=139.7034,
                municipality="新宿区",
                freshness=Freshness.STALE,
            ),
            _resource(
                "mental-current-far",
                TokyoResourceCategory.MENTAL_HEALTH_SUPPORT,
                latitude=35.7138,
                longitude=139.7034,
                municipality="新宿区",
                freshness=Freshness.CURRENT,
            ),
        ]
    )


def run_tokyo_evaluation(
    suite: TokyoEvaluationSuite,
    *,
    scenario_bytes: bytes | None = None,
) -> TokyoEvaluationReport:
    repository = build_tokyo_evaluation_repository()
    provider = UnavailableEvaluationProvider()
    app = create_app(
        settings=Settings(environment="test"),
        provider=provider,
        tokyo_repository=repository,
    )
    results: list[TokyoEvaluationCaseResult] = []
    with TestClient(app) as client:
        for case in suite.cases:
            results.append(_evaluate_case(client, repository, case))

    metrics = _calculate_metrics(results)
    report = TokyoEvaluationReport(
        scenario_sha256=hashlib.sha256(
            scenario_bytes
            if scenario_bytes is not None
            else json.dumps(
                suite.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        fixture_resource_count=len(repository),
        metrics=metrics,
        thresholds=suite.thresholds,
        threshold_pass=_thresholds_pass(metrics, suite.thresholds),
        cases=results,
    )
    return report


def run_tokyo_evaluation_path(path: Path = DEFAULT_SCENARIO_PATH) -> TokyoEvaluationReport:
    raw = path.read_bytes()
    suite = TokyoEvaluationSuite.model_validate_json(raw)
    return run_tokyo_evaluation(suite, scenario_bytes=raw)


def write_tokyo_evaluation_report(report: TokyoEvaluationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(_render_summary(report), encoding="utf-8")


def _evaluate_case(
    client: TestClient,
    repository: TokyoResourceRepository,
    case: TokyoEvaluationCase,
) -> TokyoEvaluationCaseResult:
    failures: list[str] = []
    expected = case.expected
    safety = assess_tokyo_safety(case.query, case.language)
    safety_ok = safety.disposition is expected.safety_disposition
    if not safety_ok:
        failures.append(
            f"safety disposition {safety.disposition.value!r} != {expected.safety_disposition.value!r}"
        )

    payload = {
        "query": case.query,
        "interface_language": case.language.value,
        "location": case.location.api_payload(),
        "radius_km": 10,
        "limit": 10,
    }
    response = client.post("/tokyo/agent/search", json=payload)
    if response.status_code != 200:
        return TokyoEvaluationCaseResult(
            case_id=case.case_id,
            tags=case.tags,
            status=f"http_{response.status_code}",
            passed=False,
            intent_tool_ok=False,
            ranking_ok=False,
            safety_ok=safety_ok,
            grounding_ok=False,
            provenance_ok=False,
            language_ok=False,
            unsupported_factual_resource_claims=0,
            returned_resource_ids=[],
            failures=[*failures, f"HTTP status {response.status_code}"],
        )

    body = response.json()
    actual_status = str(body.get("status"))
    if actual_status != expected.status:
        failures.append(f"status {actual_status!r} != {expected.status!r}")

    if actual_status == "safety_boundary":
        return _evaluate_safety_boundary(case, body, safety_ok, failures)

    intent = body.get("intent", {})
    actual_intent = intent.get("intent")
    actual_category = intent.get("category")
    search = body.get("search")
    intent_tool_ok = actual_intent == expected.intent and actual_category == expected.category
    if expected.intent is None:
        intent_tool_ok = actual_intent is None and actual_category is None and search is None
    elif search is not None:
        applied = search.get("applied_filters", {})
        intent_tool_ok = intent_tool_ok and applied.get("category") == expected.category
    if not intent_tool_ok:
        failures.append("intent/tool-selection contract mismatch")

    language_ok = intent.get("interface_language") == case.language.value
    if not language_ok:
        failures.append("interface language was not preserved")

    returned_ids: list[str] = []
    grounding_ok = True
    provenance_ok = True
    unsupported_claims = 0
    resources_by_id = {resource.resource_id: resource for resource in repository.resources}
    if search is not None:
        returned = search.get("results", [])
        returned_ids = [item["resource"]["resource_id"] for item in returned]
        for item in returned:
            payload_resource = item["resource"]
            resource_id = payload_resource["resource_id"]
            canonical = resources_by_id.get(resource_id)
            if canonical is None or payload_resource != canonical.model_dump(mode="json"):
                grounding_ok = False
                unsupported_claims += 1
            if not payload_resource.get("provenance"):
                provenance_ok = False

    ranking_ok = True
    if expected.ordered_resource_ids is not None:
        ranking_ok = returned_ids == expected.ordered_resource_ids
        if not ranking_ok:
            failures.append(
                f"resource order {returned_ids!r} != {expected.ordered_resource_ids!r}"
            )

    if expected.null_fields and returned_ids:
        first_resource = search["results"][0]["resource"]
        for field_name in expected.null_fields:
            if first_resource.get(field_name) is not None:
                grounding_ok = False
                unsupported_claims += 1
                failures.append(f"missing field {field_name!r} became a positive claim")

    if expected.freshness and search is not None:
        payload_by_id = {
            item["resource"]["resource_id"]: item["resource"] for item in search.get("results", [])
        }
        for resource_id, freshness in expected.freshness.items():
            if payload_by_id.get(resource_id, {}).get("freshness") != freshness.value:
                grounding_ok = False
                unsupported_claims += 1
                failures.append(f"freshness was not preserved for {resource_id!r}")

    if expected.explanation_model_status is not None:
        if body.get("explanation_model_status") != expected.explanation_model_status:
            failures.append("model fallback status mismatch")
            intent_tool_ok = False

    for explanation in body.get("explanations", []):
        resource_id = explanation.get("resource_id")
        canonical = resources_by_id.get(resource_id)
        if canonical is None or explanation.get("citations") != [
            citation.model_dump(mode="json") for citation in canonical.provenance
        ]:
            grounding_ok = False
            unsupported_claims += 1

    if not grounding_ok:
        failures.append("source-grounding contract mismatch")
    if not provenance_ok:
        failures.append("returned resource lacked provenance")

    passed = (
        actual_status == expected.status
        and intent_tool_ok
        and ranking_ok
        and safety_ok
        and grounding_ok
        and provenance_ok
        and language_ok
    )
    return TokyoEvaluationCaseResult(
        case_id=case.case_id,
        tags=case.tags,
        status=actual_status,
        passed=passed,
        intent_tool_ok=intent_tool_ok,
        ranking_ok=ranking_ok,
        safety_ok=safety_ok,
        grounding_ok=grounding_ok,
        provenance_ok=provenance_ok,
        language_ok=language_ok,
        unsupported_factual_resource_claims=unsupported_claims,
        returned_resource_ids=returned_ids,
        failures=failures,
    )


def _evaluate_safety_boundary(
    case: TokyoEvaluationCase,
    body: dict[str, Any],
    safety_ok: bool,
    failures: list[str],
) -> TokyoEvaluationCaseResult:
    safety_body = body.get("safety", {})
    disposition_ok = safety_body.get("disposition") == case.expected.safety_disposition.value
    bypass_ok = safety_body.get("bypass_resource_navigation") is True
    grounding_ok = bool(safety_body.get("references"))
    provenance_ok = grounding_ok and all(
        reference.get("canonical_url") and reference.get("retrieved_at")
        for reference in safety_body.get("references", [])
    )
    language_ok = True
    if case.expected.message_contains is not None:
        language_ok = case.expected.message_contains in str(safety_body.get("message", ""))
    if not disposition_ok or not bypass_ok:
        failures.append("safety boundary did not preserve escalation")
    if not grounding_ok or not provenance_ok:
        failures.append("safety boundary lacked authoritative provenance")
    if not language_ok:
        failures.append("safety response language marker missing")
    passed = (
        body.get("status") == case.expected.status
        and safety_ok
        and disposition_ok
        and bypass_ok
        and grounding_ok
        and provenance_ok
        and language_ok
    )
    return TokyoEvaluationCaseResult(
        case_id=case.case_id,
        tags=case.tags,
        status=str(body.get("status")),
        passed=passed,
        intent_tool_ok=True,
        ranking_ok=True,
        safety_ok=safety_ok and disposition_ok and bypass_ok,
        grounding_ok=grounding_ok,
        provenance_ok=provenance_ok,
        language_ok=language_ok,
        unsupported_factual_resource_claims=0,
        returned_resource_ids=[],
        failures=failures,
    )


def _calculate_metrics(results: Sequence[TokyoEvaluationCaseResult]) -> TokyoEvaluationMetrics:
    primary = [result for result in results if "primary" in result.tags]
    intent = [result for result in results if "intent" in result.tags]
    ranking = [result for result in results if "ranking" in result.tags]
    safety = [result for result in results if "safety" in result.tags]
    language = [result for result in results if "language" in result.tags or "primary" in result.tags]

    unsupported = sum(result.unsupported_factual_resource_claims for result in results)
    factual = [result for result in results if result.returned_resource_ids]
    provenance = [result for result in factual if result.provenance_ok]
    grounded = [result for result in factual if result.grounding_ok]
    return TokyoEvaluationMetrics(
        total_cases=len(results),
        passed_cases=sum(result.passed for result in results),
        primary_completion_percent=_percent(sum(result.passed for result in primary), len(primary)),
        intent_tool_selection_percent=_percent(
            sum(result.intent_tool_ok for result in intent), len(intent)
        ),
        geo_ranking_percent=_percent(sum(result.ranking_ok for result in ranking), len(ranking)),
        safety_escalation_recall_percent=_percent(
            sum(result.safety_ok for result in safety), len(safety)
        ),
        grounded_resource_claim_precision_percent=_percent(len(grounded), len(factual)),
        unsupported_factual_resource_claims=unsupported,
        provenance_presence_percent=_percent(len(provenance), len(factual)),
        language_fidelity_percent=_percent(sum(result.language_ok for result in language), len(language)),
    )


def _thresholds_pass(
    metrics: TokyoEvaluationMetrics,
    thresholds: TokyoEvaluationThresholds,
) -> bool:
    return all(
        (
            metrics.primary_completion_percent >= thresholds.primary_completion_percent,
            metrics.intent_tool_selection_percent >= thresholds.intent_tool_selection_percent,
            metrics.geo_ranking_percent >= thresholds.geo_ranking_percent,
            metrics.safety_escalation_recall_percent >= thresholds.safety_escalation_recall_percent,
            metrics.unsupported_factual_resource_claims
            <= thresholds.unsupported_factual_resource_claims_max,
            metrics.provenance_presence_percent >= thresholds.provenance_presence_percent,
            metrics.language_fidelity_percent >= thresholds.language_fidelity_percent,
        )
    )


def _percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 100.0
    return round(100.0 * numerator / denominator, 4)


def _provenance(record_id: str) -> SourceProvenance:
    return SourceProvenance(
        source_id="cp207-official-fixture",
        source_record_id=record_id,
        source_url="https://catalog.data.metro.tokyo.lg.jp/dataset/cp207-fixture",
        catalog_url="https://catalog.data.metro.tokyo.lg.jp/dataset/cp207-fixture",
        publisher="Tokyo public authority fixture",
        licence="Open data fixture",
        source_as_of=date(2026, 8, 1),
        retrieved_at=date(2026, 8, 13),
        content_sha256=hashlib.sha256(record_id.encode("utf-8")).hexdigest(),
    )


def _resource(
    resource_id: str,
    category: TokyoResourceCategory,
    *,
    latitude: float,
    longitude: float,
    municipality: str,
    languages: list[str] | None = None,
    opening_hours: str | None = "09:00-17:00",
    phone: str | None = None,
    freshness: Freshness = Freshness.CURRENT,
) -> TokyoResource:
    return TokyoResource(
        resource_id=resource_id,
        name=f"CP-207 fixture {resource_id}",
        category=category,
        address=f"東京都{municipality} CP-207 fixture",
        municipality=municipality,
        latitude=latitude,
        longitude=longitude,
        languages=languages or [],
        opening_hours=opening_hours,
        access_notes=None,
        phone=phone,
        website=None,
        freshness=freshness,
        provenance=[_provenance(resource_id)],
        data_quality_flags=[] if languages else ["language_support_unknown"],
    )


def _render_summary(report: TokyoEvaluationReport) -> str:
    metrics = report.metrics
    lines = [
        "# CP-207 Tokyo engineering evaluation",
        "",
        "This report measures reproducible software behaviour only. It does not claim clinical effectiveness.",
        "",
        f"- Threshold status: **{'PASS' if report.threshold_pass else 'FAIL'}**",
        f"- Cases passed: {metrics.passed_cases}/{metrics.total_cases}",
        f"- Primary scenario completion: {metrics.primary_completion_percent:.1f}%",
        f"- Intent/tool selection: {metrics.intent_tool_selection_percent:.1f}%",
        f"- Deterministic geo/ranking: {metrics.geo_ranking_percent:.1f}%",
        f"- Safety escalation recall: {metrics.safety_escalation_recall_percent:.1f}%",
        f"- Grounded resource-claim precision: {metrics.grounded_resource_claim_precision_percent:.1f}%",
        f"- Unsupported factual resource claims: {metrics.unsupported_factual_resource_claims}",
        f"- Provenance presence: {metrics.provenance_presence_percent:.1f}%",
        f"- Language fidelity: {metrics.language_fidelity_percent:.1f}%",
        "",
        "## Case failures",
        "",
    ]
    failed = [result for result in report.cases if not result.passed]
    if not failed:
        lines.append("None.")
    else:
        for result in failed:
            lines.append(f"- `{result.case_id}`: {'; '.join(result.failures)}")
    return "\n".join(lines) + "\n"
