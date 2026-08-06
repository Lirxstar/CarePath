#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.api.app.config import Settings
from backend.api.app.llm.radeon_cloud import RadeonCloudProvider
from backend.api.app.llm.radeon_local import RadeonLocalProvider
from backend.api.app.main import create_app


class _SilentHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class _ModelHandler(_SilentHandler):
    requests_seen = 0
    redirect_target: str | None = None

    def do_GET(self) -> None:
        type(self).requests_seen += 1
        if type(self).redirect_target is not None:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_target)
            self.end_headers()
            return
        self._write_json(200, {"data": [{"id": "privacy-test-model"}]})

    def do_POST(self) -> None:
        type(self).requests_seen += 1
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self._write_json(
            200,
            {
                "model": "privacy-test-model",
                "choices": [
                    {
                        "message": {"content": '{"status":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            },
        )


class _TrapHandler(_SilentHandler):
    requests_seen = 0

    def _record(self) -> None:
        type(self).requests_seen += 1
        self._write_json(418, {"trap": True})

    def do_GET(self) -> None:
        self._record()

    def do_POST(self) -> None:
        self._record()


@contextmanager
def _server(handler: type[BaseHTTPRequestHandler]) -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _proxy_environment(proxy_url: str) -> Iterator[None]:
    names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "no_proxy")
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(
        {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "ALL_PROXY": proxy_url,
            "NO_PROXY": "",
            "no_proxy": "",
        }
    )
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _local_settings(port: int) -> Settings:
    return Settings(
        environment="test",
        llm_provider="radeon_local",
        privacy_mode="local_strict",
        radeon_base_url=f"http://127.0.0.1:{port}",
        radeon_model_id="privacy-test-model",
        radeon_request_timeout_seconds=2.0,
    )


def _remote_provider_rejected() -> bool:
    settings = Settings(
        environment="test",
        llm_provider="radeon_cloud",
        privacy_mode="local_strict",
        radeon_cloud_api_key="synthetic-test-key",
    )
    application = create_app(settings, RadeonCloudProvider(settings))
    try:
        with TestClient(application):
            pass
    except ValueError as exc:
        return "local_strict requires" in str(exc)
    return False


def run_check() -> dict[str, Any]:
    _ModelHandler.requests_seen = 0
    _ModelHandler.redirect_target = None
    _TrapHandler.requests_seen = 0

    with _server(_TrapHandler) as trap_server, _server(_ModelHandler) as model_server:
        trap_port = int(trap_server.server_address[1])
        model_port = int(model_server.server_address[1])
        trap_url = f"http://127.0.0.1:{trap_port}"
        provider = RadeonLocalProvider(_local_settings(model_port))

        with _proxy_environment(trap_url):
            health = asyncio.run(provider.health_check())
            generated = asyncio.run(
                provider.generate_structured(
                    "Return a JSON object with status ok.",
                    {
                        "type": "object",
                        "properties": {"status": {"type": "string"}},
                        "required": ["status"],
                        "additionalProperties": False,
                    },
                )
            )

            _ModelHandler.redirect_target = f"{trap_url}/redirect-capture"
            redirected_health = asyncio.run(provider.health_check())

        remote_url_rejected = False
        try:
            Settings(
                environment="test",
                llm_provider="radeon_local",
                privacy_mode="local_strict",
                radeon_base_url="http://203.0.113.10:8000",
            )
        except ValueError:
            remote_url_rejected = True

        checks = {
            "local_provider_health_ok": health.get("status") == "ok",
            "local_structured_generation_ok": generated == {"status": "ok"},
            "environment_proxy_not_used": _TrapHandler.requests_seen == 0,
            "redirect_not_followed": redirected_health.get("status") == "unavailable",
            "remote_runtime_url_rejected": remote_url_rejected,
            "remote_provider_rejected_in_local_strict": _remote_provider_rejected(),
        }
        return {
            "schema_version": "1.0",
            "captured_at": datetime.now(UTC).isoformat(),
            "mode": "local_strict",
            "checks": checks,
            "network_observation": {
                "model_server_requests": _ModelHandler.requests_seen,
                "proxy_or_redirect_trap_requests": _TrapHandler.requests_seen,
            },
            "pass": all(checks.values()),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Produce repeatable local-only privacy and egress evidence."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/local_privacy_egress.json"),
    )
    args = parser.parse_args()

    payload = run_check()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    print(json.dumps({"pass": payload["pass"], "checks": payload["checks"]}, indent=2))
    return 0 if payload["pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
