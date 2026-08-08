import asyncio
import json
from typing import Any
from urllib.request import Request

import pytest

from backend.api.app.config import Settings
from backend.api.app.llm.local_openai import LocalOpenAIProvider
from backend.api.app.llm.mock import MockLLMProvider


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def make_local_provider() -> LocalOpenAIProvider:
    return LocalOpenAIProvider(
        Settings(
            environment="test",
            privacy_mode="local_strict",
            local_llm_base_url="http://127.0.0.1:8000",
            local_llm_model_id="metadata-test",
        )
    )


def test_base_provider_metadata_contract_is_backwards_compatible() -> None:
    provider = MockLLMProvider()

    result, metadata = asyncio.run(
        provider.generate_structured_with_metadata("hello", {"type": "object"})
    )

    assert result == {"provider": "mock", "schema": {"type": "object"}}
    assert metadata == {}


def test_local_provider_returns_only_safe_response_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse(
            {
                "id": "private-request-id-must-not-be-exported",
                "model": "metadata-test",
                "choices": [
                    {
                        "message": {"content": '{"status":"ok"}'},
                        "finish_reason": "stop",
                        "logprobs": {"private": True},
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "total_tokens": 19,
                    "cached_tokens": 5,
                },
                "system_fingerprint": "private-runtime-detail",
            }
        )

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = make_local_provider()

    result, metadata = asyncio.run(
        provider.generate_structured_with_metadata("return JSON", {"type": "object"})
    )

    assert result == {"status": "ok"}
    assert metadata == {
        "model": "metadata-test",
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
        },
    }
    serialized = json.dumps(metadata)
    assert "private-request-id" not in serialized
    assert "system_fingerprint" not in serialized
    assert "cached_tokens" not in serialized


def test_local_provider_filters_invalid_usage_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse(
            {
                "model": 123,
                "choices": [
                    {
                        "message": {"content": '{"status":"ok"}'},
                        "finish_reason": None,
                    }
                ],
                "usage": {
                    "prompt_tokens": True,
                    "completion_tokens": -1,
                    "total_tokens": 4,
                },
            }
        )

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = make_local_provider()

    _, metadata = asyncio.run(
        provider.generate_structured_with_metadata("return JSON", {"type": "object"})
    )

    assert metadata == {"usage": {"total_tokens": 4}}


def test_local_provider_omits_empty_usage_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Request, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse(
            {
                "choices": [{"message": {"content": '{"status":"ok"}'}}],
                "usage": {"prompt_tokens": "12"},
            }
        )

    monkeypatch.setattr("backend.api.app.llm.local_openai.open_loopback", fake_open)
    provider = make_local_provider()

    _, metadata = asyncio.run(
        provider.generate_structured_with_metadata("return JSON", {"type": "object"})
    )

    assert metadata == {}
