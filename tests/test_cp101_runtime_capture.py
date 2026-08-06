import json
import subprocess
from typing import Any

from evaluation.amd import capture_environment


def test_external_runtime_probe_captures_gpu_metadata_without_full_path(
    monkeypatch: Any,
) -> None:
    payload = {
        "available": True,
        "python": "3.10.16",
        "platform": "Linux",
        "torch_version": "2.9.0",
        "hip_version": "7.2.1",
        "accelerator_available": True,
        "device_count": 1,
        "devices": [
            {
                "index": 0,
                "name": "AMD Radeon Graphics",
                "total_memory_bytes": 51522830336,
                "architecture": "gfx1100",
            }
        ],
    }

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        assert args[0][0] == "/private/account/runtime/python3"
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(capture_environment.subprocess, "run", fake_run)

    result = capture_environment.external_torch_environment(
        "/private/account/runtime/python3"
    )

    assert result["accelerator_available"] is True
    assert result["hip_version"] == "7.2.1"
    assert result["devices"][0]["architecture"] == "gfx1100"
    assert result["probe_mode"] == "external_runtime"
    assert result["runtime_python_executable"] == "python3"
    assert "/private/account" not in json.dumps(result)


def test_external_runtime_probe_sanitizes_failed_process(
    monkeypatch: Any,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=9,
            stdout="",
            stderr="private account path and runtime details",
        )

    monkeypatch.setattr(capture_environment.subprocess, "run", fake_run)

    result = capture_environment.external_torch_environment("/runtime/python")

    assert result == {
        "available": False,
        "probe_mode": "external_runtime",
        "returncode": 9,
        "error_code": "runtime_probe_failed",
    }
    assert "private account" not in json.dumps(result)


def test_torch_environment_uses_configured_serving_runtime(
    monkeypatch: Any,
) -> None:
    expected = {
        "available": True,
        "probe_mode": "external_runtime",
        "hip_version": "7.2.1",
    }
    monkeypatch.setenv("CAREPATH_RADEON_RUNTIME_PYTHON", "/runtime/python")
    monkeypatch.setattr(
        capture_environment,
        "external_torch_environment",
        lambda value: expected if value == "/runtime/python" else {},
    )

    assert capture_environment.torch_environment() == expected
