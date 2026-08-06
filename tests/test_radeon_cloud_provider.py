import asyncio
import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from backend.api.app.config import Settings
from backend.api.app.llm.radeon_cloud import (
    RadeonCloudProvider,
    RadeonCloudProviderError,
)
from backend.api.app.llm.registry import available_providers, get_provider
from backend.api.app.main import create_app


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "llm_provider": "radeon_cloud",
        "privacy_mode": "standard_demo",
        "radeon_cloud_base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "radeon_cloud_model_id": "DeepSeek-V4-Flash",
        "radeon_cloud_api_key": "test-key-must-not-leak",
        "radeon_cloud_request_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_radeon_cloud_provider_is_registered_and_hosted() -> None:
    assert "radeon_cloud" in available_providers()
    provider = get_provider("radeon_cloud")
    assert isinstance(provider, RadeonCloudProvider)
    assert provider.is_local is False


def test_generate_calls_official_openai_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse({"choices": [{"message": {"content": "Radeon Cloud response"}}]})

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_cloud.urlopen",
        fake_urlopen,
    )
    provider = RadeonCloudProvider(make_settings())

    result = asyncio.run(provider.generate("synthetic prompt", max_tokens=64, seed=7))

    assert result == "Radeon Cloud response"
    assert captured["url"] == "https://developer.amd.com.cn/radeon/api/v1/chat/completions"
    assert captured["timeout"] == 1.0
    assert captured["authorization"] == "Bearer test-key-must-not-leak"
    assert captured["payload"]["model"] == "DeepSeek-V4-Flash"
    assert captured["payload"]["messages"] == [
        {"role": "user", "content": "synthetic prompt"}
    ]
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["seed"] == 7
    assert captured["payload"]["stream"] is False


def test_structured_generation_uses_schema_instruction_and_parses_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse(
            {"choices": [{"message": {"content": '{"summary":"Synthetic summary","safe":true}'}}]}
        )

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_cloud.urlopen",
        fake_urlopen,
    )
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "safe": {"type": "boolean"},
        },
        "required": ["summary", "safe"],
    }
    provider = RadeonCloudProvider(make_settings())

    result = asyncio.run(provider.generate_structured("return JSON", schema))

    assert result == {"summary": "Synthetic summary", "safe": True}
    messages = captured["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert "JSON Schema" in messages[0]["content"]
    assert '"required":["summary","safe"]' in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "return JSON"}


def test_health_check_reports_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        assert request.full_url == "https://developer.amd.com.cn/radeon/api/v1/models"
        assert request.get_header("Authorization") == "Bearer test-key-must-not-leak"
        return FakeResponse({"data": [{"id": "DeepSeek-V4-Flash"}]})

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_cloud.urlopen",
        fake_urlopen,
    )
    provider = RadeonCloudProvider(make_settings())

    assert asyncio.run(provider.health_check()) == {
        "status": "ok",
        "provider": "radeon_cloud",
        "model": "DeepSeek-V4-Flash",
        "local": False,
    }


def test_health_check_reports_missing_key_without_network() -> None:
    provider = RadeonCloudProvider(make_settings(radeon_cloud_api_key=None, llm_api_key=None))

    assert asyncio.run(provider.health_check()) == {
        "status": "not_configured",
        "provider": "radeon_cloud",
        "model": "DeepSeek-V4-Flash",
        "local": False,
        "error_code": "api_key_missing",
    }


def test_cloud_failure_does_not_expose_prompt_key_or_network_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        raise URLError("private network detail")

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_cloud.urlopen",
        failing_urlopen,
    )
    provider = RadeonCloudProvider(make_settings())

    with pytest.raises(RadeonCloudProviderError, match="Cloud is unavailable") as exc_info:
        asyncio.run(provider.generate("prompt-secret-must-not-escape"))

    serialized = str(exc_info.value)
    assert "prompt-secret-must-not-escape" not in serialized
    assert "test-key-must-not-leak" not in serialized
    assert "private network detail" not in serialized


def test_local_strict_rejects_radeon_cloud_provider() -> None:
    provider = RadeonCloudProvider(make_settings())
    application = create_app(
        make_settings(privacy_mode="local_strict"),
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


@pytest.mark.parametrize(
    "base_url",
    (
        "http://developer.amd.com.cn/radeon/api/v1",
        "https://user:password@developer.amd.com.cn/radeon/api/v1",
        "https://developer.amd.com.cn/radeon/api/v1?token=secret",
        "https://developer.amd.com.cn/radeon/api/v1#fragment",
    ),
)
def test_settings_reject_insecure_or_credential_bearing_cloud_urls(
    base_url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="credential-free HTTPS URL",
    ):
        make_settings(radeon_cloud_base_url=base_url)


def test_structured_generation_rejects_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse({"choices": [{"message": {"content": '["not","object"]'}}]})

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_cloud.urlopen",
        fake_urlopen,
    )
    provider = RadeonCloudProvider(make_settings())

    with pytest.raises(RadeonCloudProviderError, match="non-object"):
        asyncio.run(provider.generate_structured("test", {"type": "object"}))
