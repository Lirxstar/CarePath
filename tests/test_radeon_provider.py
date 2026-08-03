import asyncio
import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request

import pytest

from backend.api.app.config import Settings
from backend.api.app.llm.radeon_local import (
    RadeonLocalProvider,
    RadeonProviderError,
)
from backend.api.app.llm.registry import available_providers, get_provider


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
        "llm_provider": "radeon_local",
        "privacy_mode": "local_strict",
        "radeon_base_url": "http://127.0.0.1:8000",
        "radeon_model_id": "carepath-test",
        "radeon_request_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_radeon_provider_is_registered_and_local() -> None:
    assert "radeon_local" in available_providers()
    provider = get_provider("radeon_local")
    assert isinstance(provider, RadeonLocalProvider)
    assert provider.is_local is True


def test_generate_calls_loopback_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse(
            {"choices": [{"message": {"content": "Local Radeon response"}}]}
        )

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        fake_urlopen,
    )
    provider = RadeonLocalProvider(make_settings())

    result = asyncio.run(provider.generate("synthetic prompt", max_tokens=64, seed=7))

    assert result == "Local Radeon response"
    assert captured["url"] == "http://127.0.0.1:8000/v1/chat/completions"
    assert captured["timeout"] == 1.0
    assert captured["payload"]["model"] == "carepath-test"
    assert captured["payload"]["messages"] == [
        {"role": "user", "content": "synthetic prompt"}
    ]
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["seed"] == 7
    assert captured["payload"]["stream"] is False


def test_generate_structured_uses_vllm_schema_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"status":"ok","provider":"radeon_local"}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        fake_urlopen,
    )
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    provider = RadeonLocalProvider(make_settings())

    result = asyncio.run(provider.generate_structured("return JSON", schema))

    assert result == {"status": "ok", "provider": "radeon_local"}
    assert captured["payload"]["structured_outputs"] == {"json": schema}


def test_generate_structured_uses_llama_cpp_schema_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse(
            {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        )

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        fake_urlopen,
    )
    schema = {"type": "object"}
    provider = RadeonLocalProvider(make_settings(radeon_runtime="llama_cpp_rocm"))

    assert asyncio.run(provider.generate_structured("return JSON", schema)) == {
        "status": "ok"
    }
    assert captured["payload"]["response_format"] == {
        "type": "json_schema",
        "schema": schema,
    }


def test_health_check_reports_ready_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        assert request.full_url == "http://127.0.0.1:8000/v1/models"
        return FakeResponse({"data": [{"id": "carepath-test"}]})

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        fake_urlopen,
    )
    provider = RadeonLocalProvider(make_settings(radeon_inference_dtype="q4_k_m"))

    health = asyncio.run(provider.health_check())

    assert health == {
        "status": "ok",
        "provider": "radeon_local",
        "runtime": "vllm_rocm",
        "model": "carepath-test",
        "device": "0",
        "dtype": "q4_k_m",
        "local": True,
    }


def test_health_check_sanitizes_unavailable_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        raise URLError("private host details")

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        failing_urlopen,
    )
    provider = RadeonLocalProvider(make_settings())

    health = asyncio.run(provider.health_check())

    assert health["status"] == "unavailable"
    assert health["error_code"] == "local_runtime_unavailable"
    assert "private host details" not in json.dumps(health)


def test_generation_error_does_not_expose_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        raise URLError("network detail")

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        failing_urlopen,
    )
    provider = RadeonLocalProvider(make_settings())

    with pytest.raises(RadeonProviderError, match="runtime is unavailable") as exc_info:
        asyncio.run(provider.generate("prompt-secret-must-not-escape"))

    assert "prompt-secret-must-not-escape" not in str(exc_info.value)
    assert "network detail" not in str(exc_info.value)


@pytest.mark.parametrize(
    "base_url",
    (
        "https://127.0.0.1:8000",
        "http://192.168.1.20:8000",
        "http://example.com:8000",
        "http://user:password@127.0.0.1:8000",
        "http://127.0.0.1:8000/v1",
    ),
)
def test_settings_reject_non_loopback_or_ambiguous_runtime_urls(base_url: str) -> None:
    with pytest.raises(
        ValueError,
        match="credential-free loopback HTTP origin",
    ):
        make_settings(radeon_base_url=base_url)


def test_generation_rejects_unsupported_options_before_network() -> None:
    provider = RadeonLocalProvider(make_settings())

    with pytest.raises(ValueError, match="Unsupported Radeon generation options"):
        asyncio.run(provider.generate("test", top_p=0.9))


def test_structured_generation_rejects_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse({"choices": [{"message": {"content": '["not","object"]'}}]})

    monkeypatch.setattr(
        "backend.api.app.llm.radeon_local.urlopen",
        fake_urlopen,
    )
    provider = RadeonLocalProvider(make_settings())

    with pytest.raises(RadeonProviderError, match="non-object"):
        asyncio.run(provider.generate_structured("test", {"type": "object"}))
