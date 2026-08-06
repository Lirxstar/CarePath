from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from ..config import Settings, get_settings
from .provider import JsonObject, LLMProvider


class RadeonProviderError(RuntimeError):
    """Controlled local-runtime failure that never includes prompt content."""


class _RejectRedirects(HTTPRedirectHandler):
    """Refuse every redirect so a loopback server cannot bounce data off-host."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _open_loopback(request: Request, timeout: float) -> Any:
    """Open one request without environment proxies or HTTP redirects."""

    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    return opener.open(request, timeout=timeout)


class RadeonLocalProvider(LLMProvider):
    """Loopback client for a vLLM or llama.cpp server running on AMD ROCm."""

    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        self._base_url = self._validate_base_url(resolved.radeon_base_url)
        self._assert_loopback_resolution()
        self._model_id = resolved.radeon_model_id
        self._runtime = resolved.radeon_runtime
        self._device = resolved.radeon_device
        self._dtype = resolved.radeon_inference_dtype
        self._timeout_seconds = resolved.radeon_request_timeout_seconds
        self._max_new_tokens = resolved.radeon_max_new_tokens
        self._temperature = resolved.radeon_temperature

    @property
    def is_local(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        response = await self._chat_completion(
            prompt,
            structured_schema=None,
            **kwargs,
        )
        return self._extract_content(response)

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        result, _ = await self.generate_structured_with_metadata(prompt, schema, **kwargs)
        return result

    async def generate_structured_with_metadata(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> tuple[JsonObject, JsonObject]:
        """Return the parsed object plus non-secret OpenAI-compatible usage metadata."""

        response = await self._chat_completion(
            prompt,
            structured_schema=schema,
            **kwargs,
        )
        content = self._extract_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RadeonProviderError(
                "Local Radeon runtime returned invalid structured JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise RadeonProviderError(
                "Local Radeon runtime returned a non-object structured result"
            )
        return cast(JsonObject, parsed), self._safe_response_metadata(response)

    async def health_check(self) -> JsonObject:
        try:
            payload = await asyncio.to_thread(
                self._request_json,
                "GET",
                "/v1/models",
                None,
            )
        except RadeonProviderError:
            return {
                "status": "unavailable",
                "provider": "radeon_local",
                "runtime": self._runtime,
                "model": self._model_id,
                "device": self._device,
                "dtype": self._dtype,
                "local": True,
                "error_code": "local_runtime_unavailable",
            }

        models = payload.get("data")
        ready = isinstance(models, list) and bool(models)
        return {
            "status": "ok" if ready else "not_ready",
            "provider": "radeon_local",
            "runtime": self._runtime,
            "model": self._model_id,
            "device": self._device,
            "dtype": self._dtype,
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
            raise ValueError(f"Unsupported Radeon generation options: {unsupported}")

        request_payload: JsonObject = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
            "stream": False,
        }
        if structured_schema is not None:
            if self._runtime == "vllm_rocm":
                request_payload["structured_outputs"] = {"json": structured_schema}
            else:
                request_payload["response_format"] = {
                    "type": "json_schema",
                    "schema": structured_schema,
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
        self._assert_loopback_resolution()
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
            with _open_loopback(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RadeonProviderError(
                f"Local Radeon runtime returned HTTP {exc.code}"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RadeonProviderError("Local Radeon runtime is unavailable") from None

        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RadeonProviderError(
                "Local Radeon runtime returned an invalid JSON response"
            ) from exc
        if not isinstance(decoded, dict):
            raise RadeonProviderError("Local Radeon runtime returned a non-object response")
        return cast(JsonObject, decoded)

    def _assert_loopback_resolution(self) -> None:
        parsed = urlparse(self._base_url)
        hostname = parsed.hostname
        if hostname is None:
            raise ValueError("radeon_base_url must include a loopback hostname")
        port = parsed.port or 80
        try:
            addresses = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError("radeon_base_url loopback hostname could not be resolved") from exc
        if not addresses:
            raise ValueError("radeon_base_url loopback hostname did not resolve")
        for address in addresses:
            raw_address = str(address[4][0]).split("%", 1)[0]
            try:
                parsed_address = ipaddress.ip_address(raw_address)
            except ValueError as exc:
                raise ValueError(
                    "radeon_base_url resolved to an invalid IP address"
                ) from exc
            if not parsed_address.is_loopback:
                raise ValueError(
                    "radeon_base_url hostname must resolve only to loopback addresses"
                )

    @staticmethod
    def _extract_content(payload: JsonObject) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RadeonProviderError("Local Radeon runtime response did not include choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise RadeonProviderError("Local Radeon runtime returned an invalid choice")
        message = first.get("message")
        if not isinstance(message, dict):
            raise RadeonProviderError("Local Radeon runtime response did not include a message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RadeonProviderError("Local Radeon runtime returned empty message content")
        return content

    @staticmethod
    def _safe_response_metadata(payload: JsonObject) -> JsonObject:
        metadata: JsonObject = {}
        model = payload.get("model")
        if isinstance(model, str):
            metadata["model"] = model
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = choices[0].get("finish_reason")
            if isinstance(finish_reason, str):
                metadata["finish_reason"] = finish_reason
        usage = payload.get("usage")
        if isinstance(usage, dict):
            safe_usage: JsonObject = {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    safe_usage[key] = value
            if safe_usage:
                metadata["usage"] = safe_usage
        return metadata

    @staticmethod
    def _validate_base_url(value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("radeon_base_url must be a credential-free loopback HTTP origin")
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
