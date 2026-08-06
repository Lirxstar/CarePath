from __future__ import annotations

import asyncio
import json
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..config import Settings, get_settings
from .provider import JsonObject, LLMProvider


class RadeonCloudProviderError(RuntimeError):
    """Controlled Radeon Cloud failure that never exposes credentials or prompts."""


class RadeonCloudProvider(LLMProvider):
    """OpenAI-compatible client for AMD Radeon Cloud model APIs."""

    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        self._base_url = self._validate_base_url(resolved.radeon_cloud_base_url)
        self._model_id = resolved.radeon_cloud_model_id
        self._api_key = resolved.radeon_cloud_api_key or resolved.llm_api_key
        self._timeout_seconds = resolved.radeon_cloud_request_timeout_seconds
        self._max_new_tokens = resolved.radeon_cloud_max_new_tokens
        self._temperature = resolved.radeon_cloud_temperature

    @property
    def is_local(self) -> bool:
        return False

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        response = await self._chat_completion(
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return self._extract_content(response)

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        schema_text = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only one valid JSON object. Do not use Markdown or explanatory text. "
                    f"The object must follow this JSON Schema: {schema_text}"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = await self._chat_completion(messages=messages, **kwargs)
        content = self._extract_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RadeonCloudProviderError("Radeon Cloud returned invalid structured JSON") from exc
        if not isinstance(parsed, dict):
            raise RadeonCloudProviderError("Radeon Cloud returned a non-object structured result")
        return cast(JsonObject, parsed)

    async def health_check(self) -> JsonObject:
        if self._api_key is None:
            return {
                "status": "not_configured",
                "provider": "radeon_cloud",
                "model": self._model_id,
                "local": False,
                "error_code": "api_key_missing",
            }
        try:
            payload = await asyncio.to_thread(self._request_json, "GET", "/models", None)
        except RadeonCloudProviderError:
            return {
                "status": "unavailable",
                "provider": "radeon_cloud",
                "model": self._model_id,
                "local": False,
                "error_code": "cloud_runtime_unavailable",
            }

        models = payload.get("data")
        ready = isinstance(models, list) and bool(models)
        return {
            "status": "ok" if ready else "not_ready",
            "provider": "radeon_cloud",
            "model": self._model_id,
            "local": False,
        }

    async def _chat_completion(
        self,
        *,
        messages: list[JsonObject],
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
        seed = kwargs.pop("seed", None)
        if seed is not None:
            seed = self._bounded_int(
                seed,
                name="seed",
                minimum=0,
                maximum=2_147_483_647,
            )
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise ValueError(f"Unsupported Radeon Cloud generation options: {unsupported}")

        request_payload: JsonObject = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if seed is not None:
            request_payload["seed"] = seed
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/chat/completions",
            request_payload,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: JsonObject | None,
    ) -> JsonObject:
        if self._api_key is None:
            raise RadeonCloudProviderError("Radeon Cloud API key is not configured")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RadeonCloudProviderError(f"Radeon Cloud returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise RadeonCloudProviderError("Radeon Cloud is unavailable") from None

        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RadeonCloudProviderError(
                "Radeon Cloud returned an invalid JSON response"
            ) from exc
        if not isinstance(decoded, dict):
            raise RadeonCloudProviderError("Radeon Cloud returned a non-object response")
        return cast(JsonObject, decoded)

    @staticmethod
    def _extract_content(payload: JsonObject) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RadeonCloudProviderError("Radeon Cloud response did not include choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise RadeonCloudProviderError("Radeon Cloud returned an invalid choice")
        message = first.get("message")
        if not isinstance(message, dict):
            raise RadeonCloudProviderError("Radeon Cloud response did not include a message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RadeonCloudProviderError("Radeon Cloud returned empty message content")
        return content

    @staticmethod
    def _validate_base_url(value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("radeon_cloud_base_url must be a credential-free HTTPS URL")
        return normalized

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
