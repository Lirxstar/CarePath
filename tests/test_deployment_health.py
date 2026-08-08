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


def test_liveness_does_not_require_dependencies(monkeypatch: object) -> None:
    def fail_database() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health_module, "database_health_check", fail_database)  # type: ignore[attr-defined]
    application = create_app(TEST_SETTINGS, RaisingProvider())

    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_and_provider(monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        health_module,
        "database_health_check",
        lambda: None,
    )
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "provider": "ok"},
    }


def test_readiness_returns_503_for_database_failure(monkeypatch: object) -> None:
    def fail_database() -> None:
        raise RuntimeError("database-secret-must-not-escape")

    monkeypatch.setattr(health_module, "database_health_check", fail_database)  # type: ignore[attr-defined]
    application = create_app(TEST_SETTINGS, MockLLMProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "provider": "ok"},
    }
    assert "database-secret" not in response.text


def test_readiness_returns_503_for_provider_failure(monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        health_module,
        "database_health_check",
        lambda: None,
    )
    application = create_app(TEST_SETTINGS, UnreadyProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "provider": "error"},
    }
    assert "must-not-escape" not in response.text


def test_readiness_sanitizes_provider_exceptions(monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        health_module,
        "database_health_check",
        lambda: None,
    )
    application = create_app(TEST_SETTINGS, RaisingProvider())

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "provider": "error"},
    }
    assert "provider-secret" not in response.text
