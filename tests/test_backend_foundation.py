import asyncio
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.app.config import Settings, get_settings
from backend.api.app.errors import CarePathError
from backend.api.app.llm.mock import MockLLMProvider
from backend.api.app.llm.provider import JsonObject
from backend.api.app.llm.registry import (
    available_providers,
    get_provider,
    register_provider,
)
from backend.api.app.logging import CarePathJsonFormatter
from backend.api.app.main import create_app

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


class ReplacementProvider(MockLLMProvider):
    async def health_check(self) -> JsonObject:
        return {"status": "ok", "provider": "replacement"}


class LifecycleProvider(MockLLMProvider):
    def __init__(self) -> None:
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


class HostedProvider(LifecycleProvider):
    @property
    def is_local(self) -> bool:
        return False


class FailingProvider(MockLLMProvider):
    async def health_check(self) -> JsonObject:
        raise RuntimeError("prompt-and-key-must-not-escape")


def test_health_endpoint_uses_configured_provider() -> None:
    application = create_app(TEST_SETTINGS, ReplacementProvider())
    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "replacement"}
    assert response.headers["X-Request-ID"]


def test_request_id_roundtrip() -> None:
    application = create_app(TEST_SETTINGS)
    with TestClient(application) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-id"})

    assert response.headers["X-Request-ID"] == "test-id"


def test_invalid_request_id_is_replaced() -> None:
    application = create_app(TEST_SETTINGS)
    with TestClient(application) as client:
        response = client.get("/health", headers={"X-Request-ID": "contains spaces"})

    request_id = response.headers["X-Request-ID"]
    assert request_id != "contains spaces"
    assert re.fullmatch(r"[0-9a-f-]{36}", request_id)


def test_all_error_paths_use_the_same_envelope_and_request_id() -> None:
    application = create_app(TEST_SETTINGS)

    @application.get("/test/carepath-error")
    async def carepath_error() -> None:
        raise CarePathError("conflict", "Controlled conflict", status_code=409)

    @application.get("/test/generic-error")
    async def generic_error() -> None:
        raise RuntimeError("sensitive payload must not escape")

    @application.get("/test/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=418, detail="secret detail must not escape")

    @application.get("/test/items/{item_id}")
    async def typed_path(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    cases = (
        ("GET", "/missing", 404, "not_found"),
        ("POST", "/health", 405, "method_not_allowed"),
        ("GET", "/test/items/not-an-int", 422, "validation_error"),
        ("GET", "/test/carepath-error", 409, "conflict"),
        ("GET", "/test/http-error", 418, "http_error"),
        ("GET", "/test/generic-error", 500, "internal_error"),
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        for method, path, status_code, code in cases:
            response = client.request(
                method,
                path,
                headers={"X-Request-ID": "error-test-id"},
            )
            payload = response.json()

            assert response.status_code == status_code
            assert response.headers["X-Request-ID"] == "error-test-id"
            assert set(payload) == {"error"}
            assert set(payload["error"]) == {"code", "message", "request_id"}
            assert payload["error"]["code"] == code
            assert payload["error"]["request_id"] == "error-test-id"
            assert "sensitive payload" not in payload["error"]["message"]
            assert "secret detail" not in payload["error"]["message"]


def test_request_log_is_json_metadata_only() -> None:
    application = create_app(TEST_SETTINGS)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(CarePathJsonFormatter())
    carepath_logger = logging.getLogger("carepath")
    carepath_logger.addHandler(handler)

    try:
        with TestClient(application) as client:
            response = client.get(
                "/health?journal=must-not-appear",
                headers={
                    "Authorization": "Bearer must-not-appear",
                    "X-Request-ID": "log-test-id",
                },
            )
        assert response.status_code == 200
    finally:
        carepath_logger.removeHandler(handler)

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    completed = next(event for event in events if event["message"] == "request_completed")
    serialized = json.dumps(events)
    assert completed["request_id"] == "log-test-id"
    assert completed["route"] == "/health"
    assert completed["status_code"] == 200
    assert "duration_ms" in completed
    assert "must-not-appear" not in serialized
    assert "Authorization" not in serialized


def test_provider_exception_is_controlled_and_not_logged_verbatim() -> None:
    application = create_app(TEST_SETTINGS, FailingProvider())
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(CarePathJsonFormatter())
    carepath_logger = logging.getLogger("carepath")
    carepath_logger.addHandler(handler)

    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get(
                "/health?journal=query-secret",
                headers={
                    "Authorization": "Bearer header-secret",
                    "X-Request-ID": "provider-error-id",
                },
            )
    finally:
        carepath_logger.removeHandler(handler)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "provider-error-id"
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "request_id": "provider-error-id",
        }
    }
    serialized = stream.getvalue()
    assert "RuntimeError" in serialized
    assert "prompt-and-key-must-not-escape" not in serialized
    assert "query-secret" not in serialized
    assert "header-secret" not in serialized


def test_mock_provider_contract() -> None:
    provider = MockLLMProvider()
    assert asyncio.run(provider.generate("hello")) == "Mock response"
    assert asyncio.run(provider.generate_structured("hello", {"type": "object"})) == {
        "provider": "mock",
        "schema": {"type": "object"},
    }
    assert asyncio.run(provider.health_check()) == {"status": "ok", "provider": "mock"}


def test_provider_can_be_replaced_without_workflow_changes() -> None:
    register_provider("replacement", ReplacementProvider, replace=True)
    assert isinstance(get_provider("replacement"), ReplacementProvider)
    assert {"mock", "replacement"}.issubset(available_providers())


def test_settings_select_registered_provider_for_api() -> None:
    register_provider("replacement-api", ReplacementProvider, replace=True)
    application = create_app(
        Settings(environment="test", llm_provider="replacement-api"),
    )

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.json() == {"status": "ok", "provider": "replacement"}


def test_registry_rejects_invalid_provider_factory() -> None:
    def invalid_factory() -> Any:
        return object()

    register_provider("invalid-test-provider", invalid_factory, replace=True)
    with pytest.raises(TypeError, match="did not return LLMProvider"):
        get_provider("invalid-test-provider")


def test_provider_is_closed_once_after_application_shutdown() -> None:
    provider = LifecycleProvider()
    application = create_app(TEST_SETTINGS, provider)

    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert provider.close_count == 0

    assert provider.close_count == 1


def test_local_strict_rejects_hosted_provider() -> None:
    provider = HostedProvider()
    application = create_app(
        Settings(environment="test", privacy_mode="local_strict"),
        provider,
    )
    with (
        pytest.raises(
            ValueError,
            match="local_strict requires an operator-controlled local LLM provider",
        ),
        TestClient(application),
    ):
        pass
    assert provider.close_count == 1


def test_settings_load_explicit_env_file_and_mask_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "carepath.env"
    env_file.write_text(
        "\n".join(
            (
                "CAREPATH_APP_NAME=CarePath Test API",
                "CAREPATH_ENVIRONMENT=test",
                "CAREPATH_LLM_API_KEY=do-not-log-this-secret",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAREPATH_ENV_FILE", str(env_file))
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.app_name == "CarePath Test API"
        assert settings.environment == "test"
        assert settings.llm_api_key is not None
        assert settings.llm_api_key.get_secret_value() == "do-not-log-this-secret"
        assert "do-not-log-this-secret" not in repr(settings)
    finally:
        get_settings.cache_clear()


def test_invalid_settings_fail_fast() -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        Settings(log_level="not-a-level")
    with pytest.raises(ValueError, match="provider name must not be empty"):
        Settings(llm_provider=" ")


def test_create_app_returns_fastapi_application() -> None:
    assert isinstance(create_app(TEST_SETTINGS), FastAPI)


def test_uvicorn_raw_access_log_is_disabled() -> None:
    create_app(TEST_SETTINGS)
    assert logging.getLogger("uvicorn.access").disabled is True
