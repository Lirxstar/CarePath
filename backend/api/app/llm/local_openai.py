from __future__ import annotations

import asyncio
import json
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ..config import Settings, get_settings
from .provider import JsonObject, LLMProvider
from .transport_security import assert_loopback_resolution, open_loopback


class LocalProviderError(RuntimeError):
    """Controlled local-runtime failure that never includes prompt or host details."""


class LocalOpenAIProvider(LLMProvider):
    """Loopback-only client for an OpenAI-compatible local model server."""

    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        self._base_url = resolved.local_llm_base_url
        assert_loopback_resolution(self._base_url)
        self._model_id = resolved.local_llm_model_id
        self._structured_output_mode = resolved.local_llm_structured_output_mode
        self._timeout_seconds = resolved.local_llm_request_timeout_seconds
        self._max_new_tokens = resolved.local_llm_max_new_tokens
        self._temperature = resolved.local_llm_temperature

    @property
    def is_local(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        response = await self._chat_completion(prompt, structured_schema=None, **kwargs)
        return self._extract_content(response)

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        response = await self._chat_completion(prompt, structured_schema=schema, **kwargs)
        content = self._extract_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LocalProviderError("Local LLM runtime returned invalid structured JSON") from exc
        if not isinstance(parsed, dict):
            raise LocalProviderError("Local LLM runtime returned a non-object structured result")
        return cast(JsonObject, parsed)

    async def health_check(self) -> JsonObject:
        try:
            payload = await asyncio.to_thread(self._request_json, "GET", "/v1/models", None)
        except LocalProviderError:
            return {
                "status": "unavailable",
                "provider": "local_openai",
                "model": self._model_id,
                "local": True,
                "error_code": "local_runtime_unavailable",
            }

        models = payload.get("data")
        ready = isinstance(models, list) and bool(models)
        return {
            "status": "ok" if ready else "not_ready",
            "provider": "local_openai",
            "model": self._model_id,
            "local": True,
        }

    async def _chat_completion(
        self,
        prompt: str,
        *,
        structured_schema: JsonObject | None,
        **kwargs: Any,
    ) -> JsonObject:
        max_tokens = self._bounded_int(
            kwargs.pop("max_tokens", self._max_new_tokens),
            name="max_tokens",
            minimum=1,
            maximum=4096,
        )
        temperature = self._bounded_float(
            kwargs.pop("temperature", self._temperature),
            name="temperature",
            minimum=0.0,
            maximum=2.0,
        )
        seed = self._bounded_int(
            kwargs.pop("seed", 0),
            name="seed",
            minimum=0,
            maximum=2_147_483_647,
        )
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise ValueError(f"Unsupported local generation options: {unsupported}")

        request_payload: JsonObject = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
            "stream": False,
        }
        if structured_schema is not None:
            if self._structured_output_mode == "vllm_json":
                request_payload["structured_outputs"] = {"json": structured_schema}
            else:
                request_payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "carepath_result",
                        "schema": structured_schema,
                        "strict": True,
                    },
                }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/v1/chat/completions",
            request_payload,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: JsonObject | None,
    ) -> JsonObject:
        assert_loopback_resolution(self._base_url)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Connection": "close",
                "Content-Type": "application/json",
            },
        )
        try:
            with open_loopback(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise LocalProviderError(f"Local LLM runtime returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise LocalProviderError("Local LLM runtime is unavailable") from None

        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LocalProviderError("Local LLM runtime returned an invalid JSON response") from exc
        if not isinstance(decoded, dict):
            raise LocalProviderError("Local LLM runtime returned a non-object response")
        return cast(JsonObject, decoded)

    @staticmethod
    def _extract_content(payload: JsonObject) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LocalProviderError("Local LLM runtime response did not include choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LocalProviderError("Local LLM runtime returned an invalid choice")
        message = first.get("message")
        if not isinstance(message, dict):
            raise LocalProviderError("Local LLM runtime response did not include a message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalProviderError("Local LLM runtime returned empty message content")
        return content

    @staticmethod
    def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _bounded_float(
        value: Any,
        *,
        name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be numeric")
        result = float(value)
        if not minimum <= result <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return result
