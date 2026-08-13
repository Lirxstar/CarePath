from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.evaluation.tokyo import (
    UnavailableEvaluationProvider,
    build_tokyo_evaluation_repository,
)
from backend.tokyo.search import TokyoResourceRepository


def test_tokyo_readiness_reports_grounded_data_and_model_status() -> None:
    app = create_app(
        settings=Settings(environment="test", llm_provider="mock"),
        tokyo_repository=build_tokyo_evaluation_repository(),
    )

    with TestClient(app) as client:
        response = client.get("/health/tokyo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"] == {"resource_data": "ok", "provider": "ok"}
    assert payload["resource_count"] == 8
    assert payload["deterministic_search_available"] is True
    assert payload["model_assistance_available"] is True


def test_tokyo_readiness_keeps_search_ready_when_model_provider_is_unavailable() -> None:
    app = create_app(
        settings=Settings(environment="test"),
        provider=UnavailableEvaluationProvider(),
        tokyo_repository=build_tokyo_evaluation_repository(),
    )

    with TestClient(app) as client:
        readiness = client.get("/health/tokyo")
        search = client.post(
            "/tokyo/agent/search",
            json={
                "query": "I need family support near me.",
                "interface_language": "en",
                "location": {"mode": "municipality", "municipality": "江東区"},
                "radius_km": 10,
                "limit": 5,
            },
        )

    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["status"] == "ready"
    assert payload["checks"] == {"resource_data": "ok", "provider": "fallback"}
    assert payload["deterministic_search_available"] is True
    assert payload["model_assistance_available"] is False
    assert search.status_code == 200
    assert search.json()["status"] == "ok"
    assert search.json()["search"]["count"] == 1
    assert search.json()["explanation_model_status"] == "unavailable"


def test_tokyo_readiness_fails_when_source_backed_resource_corpus_is_missing() -> None:
    app = create_app(
        settings=Settings(environment="test", llm_provider="mock"),
        tokyo_repository=TokyoResourceRepository([]),
    )

    with TestClient(app) as client:
        response = client.get("/health/tokyo")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["resource_data"] == "error"
    assert payload["resource_count"] == 0
    assert payload["deterministic_search_available"] is False


def test_render_uses_liveness_while_cp208_verifier_requires_tokyo_readiness() -> None:
    render = Path("render.yaml").read_text(encoding="utf-8")
    verifier = Path("deployment/verify_tokyo_public.py").read_text(encoding="utf-8")

    assert "healthCheckPath: /health/live" in render
    assert 'fetch_json(base_url, "/health/tokyo")' in verifier
    assert 'tokyo.get("status") != "ready"' in verifier


def test_public_tokyo_playwright_contract_covers_deployment_requirements() -> None:
    spec = Path("apps/mobile/e2e/tokyo_public.spec.ts").read_text(encoding="utf-8")

    assert 'page.goto("/tokyo")' in spec
    assert "page.reload()" in spec
    assert "tokyo-language-en" in spec
    assert "tokyo-language-ja" in spec
    assert "tokyo-language-zh" in spec
    assert "tokyo-use-manual-location" in spec
    assert "tokyo-example-cooling" in spec
    assert "tokyo-directions-" in spec
    assert "tokyo-source-" in spec
