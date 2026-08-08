import asyncio
import json
import socket
from typing import Any
from urllib.error import URLError
from urllib.request import Request

import pytest

from backend.api.app.config import Settings
from backend.api.app.llm.local_openai import LocalOpenAIProvider, LocalProviderError
from backend.api.app.llm.registry import available_providers, get_provider


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "llm_provider": "local_openai",
        "privacy_mode": "local_strict",
        "local_llm_base_url": "http://127.0.0.1:8000",
        "local_llm_model_id": "carepath-test",
        "local_llm_request_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_local_provider_is_registered_and_local() -> None:
    assert "local_openai" in available_providers()
    provider = get_provider("local_openai")
    assert isinstance(provider, LocalOpenAIProvider)
    assert provider.is_local is True


def test_generate_calls_loopback_chat_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: Request, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse({"choices": [{"message": {"content": "Local response"}}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    result = asyncio.run(provider.generate("synthetic prompt", max_tokens=64, seed=7))

    assert result == "Local response"
    assert captured["url"] == "http://127.0.0.1:8000/v1/chat/completions"
    assert captured["timeout"] == 1.0
    assert captured["payload"]["model"] == "carepath-test"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "synthetic prompt"}]
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["seed"] == 7
    assert captured["payload"]["stream"] is False


def test_generate_structured_uses_openai_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse({"choices": [{"message": {"content": '{"status":"ok"}'}}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    provider = LocalOpenAIProvider(make_settings())

    assert asyncio.run(provider.generate_structured("return JSON", schema)) == {"status": "ok"}
    assert captured["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "carepath_result",
            "schema": schema,
            "strict": True,
        },
    }


def test_generate_structured_uses_vllm_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return FakeResponse({"choices": [{"message": {"content": '{"status":"ok"}'}}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    schema = {"type": "object"}
    provider = LocalOpenAIProvider(make_settings(local_llm_structured_output_mode="vllm_json"))

    assert asyncio.run(provider.generate_structured("return JSON", schema)) == {"status": "ok"}
    assert captured["payload"]["structured_outputs"] == {"json": schema}


def test_health_check_reports_ready_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del timeout
        assert request.full_url == "http://127.0.0.1:8000/v1/models"
        return FakeResponse({"data": [{"id": "carepath-test"}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    assert asyncio.run(provider.health_check()) == {
        "status": "ok",
        "provider": "local_openai",
        "model": "carepath-test",
        "local": True,
    }


def test_health_check_reports_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse({"data": []})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    assert asyncio.run(provider.health_check())["status"] == "not_ready"


def test_health_check_sanitizes_unavailable_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        raise URLError("private host details")

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", failing_open)
    provider = LocalOpenAIProvider(make_settings())

    health = asyncio.run(provider.health_check())

    assert health["status"] == "unavailable"
    assert health["error_code"] == "local_runtime_unavailable"
    assert "private host details" not in json.dumps(health)


def test_generation_error_does_not_expose_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        raise URLError("network detail")

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", failing_open)
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(LocalProviderError, match="runtime is unavailable") as exc_info:
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
        "http://127.0.0.1:8000?x=1",
    ),
)
def test_settings_reject_non_loopback_or_ambiguous_runtime_urls(base_url: str) -> None:
    with pytest.raises(ValueError, match="credential-free loopback HTTP origin"):
        make_settings(local_llm_base_url=base_url)


def test_provider_rejects_loopback_name_that_resolves_off_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = socket.getaddrinfo

    def fake_getaddrinfo(host: str, port: int, **kwargs: Any) -> list[Any]:
        if host == "localhost":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.4", port))]
        return original(host, port, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="resolve only to loopback"):
        LocalOpenAIProvider(make_settings(local_llm_base_url="http://localhost:8000"))


def test_generation_rejects_unsupported_options_before_network() -> None:
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(ValueError, match="Unsupported local generation options"):
        asyncio.run(provider.generate("test", top_p=0.9))


@pytest.mark.parametrize(
    ("kwargs", "error"),
    (
        ({"max_tokens": True}, "max_tokens must be an integer"),
        ({"max_tokens": 0}, "max_tokens must be between"),
        ({"temperature": "warm"}, "temperature must be numeric"),
        ({"temperature": 3.0}, "temperature must be between"),
        ({"seed": -1}, "seed must be between"),
    ),
)
def test_generation_validates_bounded_options(kwargs: dict[str, Any], error: str) -> None:
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises((TypeError, ValueError), match=error):
        asyncio.run(provider.generate("test", **kwargs))


def test_structured_generation_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse({"choices": [{"message": {"content": "not-json"}}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(LocalProviderError, match="invalid structured JSON"):
        asyncio.run(provider.generate_structured("test", {"type": "object"}))


def test_structured_generation_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse({"choices": [{"message": {"content": '["not","object"]'}}]})

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(LocalProviderError, match="non-object"):
        asyncio.run(provider.generate_structured("test", {"type": "object"}))


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"choices": []},
        {"choices": ["bad-choice"]},
        {"choices": [{}]},
        {"choices": [{"message": {"content": ""}}]},
    ),
)
def test_generation_rejects_malformed_chat_responses(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse(payload)

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(LocalProviderError):
        asyncio.run(provider.generate("test"))


def test_generation_rejects_non_object_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse(["not", "object"])

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = LocalOpenAIProvider(make_settings())

    with pytest.raises(LocalProviderError, match="non-object response"):
        asyncio.run(provider.generate("test"))
