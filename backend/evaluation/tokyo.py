"""Fixed CP-207 engineering evaluation for CarePath Tokyo.

The evaluator executes the real Tokyo agent HTTP route against a small versioned,
source-backed fixture repository. The model provider is intentionally unavailable so
CI needs no credentials and the product fallback path is exercised. This is software
acceptance testing, not clinical validation.
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
        return self.model_dump(exclude_none=True)


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
    """Credential-free provider that forces the supported fallback behaviour."""

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
    return TokyoResourceRepository(_fixture_resources())


def run_tokyo_evaluation(
    suite: TokyoEvaluationSuite,
    *,
    scenario_bytes: bytes | None = None,
) -> TokyoEvaluationReport:
    repository = build_tokyo_evaluation_repository()
    app = create_app(
        settings=Settings(environment="test"),
        provider=UnavailableEvaluationProvider(),
        tokyo_repository=repository,
    )
    results: list[TokyoEvaluationCaseResult] = []
    with TestClient(app) as client:
        for case in suite.cases:
            results.append(_evaluate_case(client, repository, case))

    metrics = _calculate_metrics(results)
    canonical_bytes = scenario_bytes or json.dumps(
        suite.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return TokyoEvaluationReport(
        scenario_sha256=hashlib.sha256(canonical_bytes).hexdigest(),
        fixture_resource_count=len(repository),
        metrics=metrics,
        thresholds=suite.thresholds,
        threshold_pass=_thresholds_pass(metrics, suite.thresholds),
        cases=results,
    )


def run_tokyo_evaluation_path(path: Path = DEFAULT_SCENARIO_PATH) -> TokyoEvaluationReport:
    raw = path.read_bytes()
    return run_tokyo_evaluation(TokyoEvaluationSuite.model_validate_json(raw), scenario_bytes=raw)


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
            f"safety disposition {safety.disposition.value!r} != "
            f"{expected.safety_disposition.value!r}"
        )

    response = client.post(
        "/tokyo/agent/search",
        json={
            "query": case.query,
            "interface_language": case.language.value,
            "location": case.location.api_payload(),
            "radius_km": 10,
            "limit": 10,
        },
    )
    if response.status_code != 200:
        return _http_failure(case, safety_ok, response.status_code, failures)

    body: dict[str, Any] = response.json()
    actual_status = str(body.get("status"))
    if actual_status != expected.status:
        failures.append(f"status {actual_status!r} != {expected.status!r}")
    if actual_status == "safety_boundary":
        return _evaluate_safety_boundary(case, body, safety_ok, failures)

    intent = body.get("intent", {})
    search = body.get("search")
    intent_tool_ok = _intent_tool_ok(intent, search, expected)
    if not intent_tool_ok:
        failures.append("intent/tool-selection contract mismatch")

    language_ok = intent.get("interface_language") == case.language.value
    if not language_ok:
        failures.append("interface language was not preserved")

    returned_ids, grounding_ok, provenance_ok, unsupported_claims = _audit_resources(
        repository,
        search,
    )
    ranking_ok = (
        expected.ordered_resource_ids is None or returned_ids == expected.ordered_resource_ids
    )
    if not ranking_ok:
        failures.append(f"resource order {returned_ids!r} != {expected.ordered_resource_ids!r}")

    if search is not None:
        unsupported_claims += _audit_special_source_state(expected, search, failures)
        grounding_ok = grounding_ok and unsupported_claims == 0

    if expected.explanation_model_status is not None and (
        body.get("explanation_model_status") != expected.explanation_model_status
    ):
        failures.append("model fallback status mismatch")
        intent_tool_ok = False

    explanation_claims = _audit_explanations(repository, body.get("explanations", []))
    unsupported_claims += explanation_claims
    grounding_ok = grounding_ok and explanation_claims == 0

    if not grounding_ok:
        failures.append("source-grounding contract mismatch")
    if not provenance_ok:
        failures.append("returned resource lacked provenance")

    passed = all(
        (
            actual_status == expected.status,
            intent_tool_ok,
            ranking_ok,
            safety_ok,
            grounding_ok,
            provenance_ok,
            language_ok,
        )
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


def _intent_tool_ok(
    intent: dict[str, Any],
    search: dict[str, Any] | None,
    expected: TokyoEvaluationExpected,
) -> bool:
    if expected.intent is None:
        return intent.get("intent") is None and intent.get("category") is None and search is None
    if intent.get("intent") != expected.intent or intent.get("category") != expected.category:
        return False
    if search is None:
        return False
    return search.get("applied_filters", {}).get("category") == expected.category


def _audit_resources(
    repository: TokyoResourceRepository,
    search: dict[str, Any] | None,
) -> tuple[list[str], bool, bool, int]:
    if search is None:
        return [], True, True, 0
    returned_ids: list[str] = []
    grounding_ok = True
    provenance_ok = True
    unsupported = 0
    for item in search.get("results", []):
        payload_resource = item["resource"]
        resource_id = payload_resource["resource_id"]
        returned_ids.append(resource_id)
        canonical = repository.get(resource_id)
        if canonical is None or payload_resource != canonical.model_dump(mode="json"):
            grounding_ok = False
            unsupported += 1
        if not payload_resource.get("provenance"):
            provenance_ok = False
    return returned_ids, grounding_ok, provenance_ok, unsupported


def _audit_special_source_state(
    expected: TokyoEvaluationExpected,
    search: dict[str, Any],
    failures: list[str],
) -> int:
    unsupported = 0
    results = search.get("results", [])
    if expected.null_fields and results:
        first_resource = results[0]["resource"]
        for field_name in expected.null_fields:
            if first_resource.get(field_name) is not None:
                unsupported += 1
                failures.append(f"missing field {field_name!r} became a positive claim")

    payload_by_id = {item["resource"]["resource_id"]: item["resource"] for item in results}
    for resource_id, freshness in expected.freshness.items():
        if payload_by_id.get(resource_id, {}).get("freshness") != freshness.value:
            unsupported += 1
            failures.append(f"freshness was not preserved for {resource_id!r}")
    return unsupported


def _audit_explanations(
    repository: TokyoResourceRepository,
    explanations: list[dict[str, Any]],
) -> int:
    unsupported = 0
    for explanation in explanations:
        canonical = repository.get(str(explanation.get("resource_id", "")))
        if canonical is None:
            unsupported += 1
            continue
        expected_citations = [citation.model_dump(mode="json") for citation in canonical.provenance]
        if explanation.get("citations") != expected_citations:
            unsupported += 1
    return unsupported


def _evaluate_safety_boundary(
    case: TokyoEvaluationCase,
    body: dict[str, Any],
    safety_ok: bool,
    failures: list[str],
) -> TokyoEvaluationCaseResult:
    safety_body = body.get("safety", {})
    disposition_ok = safety_body.get("disposition") == case.expected.safety_disposition.value
    bypass_ok = safety_body.get("bypass_resource_navigation") is True
    references = safety_body.get("references", [])
    grounding_ok = bool(references)
    provenance_ok = grounding_ok and all(
        reference.get("canonical_url") and reference.get("retrieved_at") for reference in references
    )
    language_ok = case.expected.message_contains is None or (
        case.expected.message_contains in str(safety_body.get("message", ""))
    )
    if not disposition_ok or not bypass_ok:
        failures.append("safety boundary did not preserve escalation")
    if not grounding_ok or not provenance_ok:
        failures.append("safety boundary lacked authoritative provenance")
    if not language_ok:
        failures.append("safety response language marker missing")
    passed = all(
        (
            body.get("status") == case.expected.status,
            safety_ok,
            disposition_ok,
            bypass_ok,
            grounding_ok,
            provenance_ok,
            language_ok,
        )
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


def _http_failure(
    case: TokyoEvaluationCase,
    safety_ok: bool,
    status_code: int,
    failures: list[str],
) -> TokyoEvaluationCaseResult:
    return TokyoEvaluationCaseResult(
        case_id=case.case_id,
        tags=case.tags,
        status=f"http_{status_code}",
        passed=False,
        intent_tool_ok=False,
        ranking_ok=False,
        safety_ok=safety_ok,
        grounding_ok=False,
        provenance_ok=False,
        language_ok=False,
        unsupported_factual_resource_claims=0,
        returned_resource_ids=[],
        failures=[*failures, f"HTTP status {status_code}"],
    )


def _calculate_metrics(results: Sequence[TokyoEvaluationCaseResult]) -> TokyoEvaluationMetrics:
    primary = _tagged(results, "primary")
    intent = _tagged(results, "intent")
    ranking = _tagged(results, "ranking")
    safety = _tagged(results, "safety")
    language = [
        result for result in results if "language" in result.tags or "primary" in result.tags
    ]
    factual = [result for result in results if result.returned_resource_ids]
    unsupported = sum(result.unsupported_factual_resource_claims for result in results)
    return TokyoEvaluationMetrics(
        total_cases=len(results),
        passed_cases=sum(result.passed for result in results),
        primary_completion_percent=_percent(sum(result.passed for result in primary), len(primary)),
        intent_tool_selection_percent=_percent(
            sum(result.intent_tool_ok for result in intent),
            len(intent),
        ),
        geo_ranking_percent=_percent(sum(result.ranking_ok for result in ranking), len(ranking)),
        safety_escalation_recall_percent=_percent(
            sum(result.safety_ok for result in safety),
            len(safety),
        ),
        grounded_resource_claim_precision_percent=_percent(
            sum(result.grounding_ok for result in factual),
            len(factual),
        ),
        unsupported_factual_resource_claims=unsupported,
        provenance_presence_percent=_percent(
            sum(result.provenance_ok for result in factual),
            len(factual),
        ),
        language_fidelity_percent=_percent(
            sum(result.language_ok for result in language),
            len(language),
        ),
    )


def _tagged(
    results: Sequence[TokyoEvaluationCaseResult],
    tag: str,
) -> list[TokyoEvaluationCaseResult]:
    return [result for result in results if tag in result.tags]


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


def _fixture_resources() -> tuple[TokyoResource, ...]:
    return (
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
    )


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
        address=f"Tokyo {municipality} CP-207 fixture",
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
        (
            "- Grounded resource-claim precision: "
            f"{metrics.grounded_resource_claim_precision_percent:.1f}%"
        ),
        f"- Unsupported factual resource claims: {metrics.unsupported_factual_resource_claims}",
        f"- Provenance presence: {metrics.provenance_presence_percent:.1f}%",
        f"- Language fidelity: {metrics.language_fidelity_percent:.1f}%",
        "",
        "## Case failures",
        "",
    ]
    failed = [result for result in report.cases if not result.passed]
    if failed:
        lines.extend(f"- `{result.case_id}`: {'; '.join(result.failures)}" for result in failed)
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"
