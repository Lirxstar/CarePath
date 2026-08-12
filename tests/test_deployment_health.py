import pytest
from fastapi.testclient import TestClient

import backend.api.app.health as health_module
from backend.api.app.config import Settings
from backend.api.app.llm.mock import MockLLMProvider
from backend.api.app.llm.provider import JsonObject
from backend.api.app.main import create_app

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


class UnreadyProvider(MockLLMProvider):
    async def health_check(self) -> JsonObject:
        return {"status": "error", "detail": "must-not-escape"}


class RaisingProvider(MockLLMProvider):
    async def health_check(self) -> JsonObject:
        raise RuntimeError("provider-secret-must-not-escape")


def test_liveness_does_not_require_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_database() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health_module, "database_health_check", fail_database)
    application = create_app(TEST_SETTINGS, RaisingProvider())

    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_build_identity_reports_platform_commit_without_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAREPATH_BUILD_COMMIT", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "git_commit": "a" * 40}
    assert response.headers["cache-control"] == "no-store"


def test_build_identity_prefers_operator_commit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    monkeypatch.setenv("CAREPATH_BUILD_COMMIT", "b" * 40)
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/build")

    assert response.json() == {"status": "ok", "git_commit": "b" * 40}


def test_build_identity_is_explicitly_unknown_without_deployment_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAREPATH_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/build")

    assert response.json() == {"status": "ok", "git_commit": None}


def test_readiness_reports_database_and_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "database_health_check", lambda: None)
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "provider": "ok"},
    }


def test_readiness_returns_503_for_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_database() -> None:
        raise RuntimeError("database-secret-must-not-escape")

    monkeypatch.setattr(health_module, "database_health_check", fail_database)
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "provider": "ok"},
    }
    assert "database-secret" not in response.text


def test_readiness_returns_503_for_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "database_health_check", lambda: None)
    application = create_app(TEST_SETTINGS, UnreadyProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "provider": "error"},
    }
    assert "must-not-escape" not in response.text


def test_readiness_sanitizes_provider_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "database_health_check", lambda: None)
    application = create_app(TEST_SETTINGS, RaisingProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "provider": "error"},
    }
    assert "provider-secret" not in response.text
