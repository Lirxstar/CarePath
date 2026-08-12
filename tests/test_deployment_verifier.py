from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deployment import verify_backend


def _base_payload(path: str, *, commit: str = "a" * 40) -> dict[str, Any]:
    if path == "/health/live":
        return {"status": "ok"}
    if path == "/health/ready":
        return {"status": "ready", "checks": {"database": "ok", "provider": "ok"}}
    if path == "/openapi.json":
        return {"info": {"title": "CarePath API"}}
    if path == "/health/build":
        return {"status": "ok", "git_commit": commit}
    raise AssertionError(f"unexpected path: {path}")


def test_legacy_verification_does_not_require_build_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_fetch(base_url: str, path: str) -> dict[str, Any]:
        assert base_url == "https://carepath.example"
        calls.append(path)
        return _base_payload(path)

    monkeypatch.setattr(verify_backend, "fetch_json", fake_fetch)

    report = verify_backend.verify("https://carepath.example")

    assert report["openapi_title"] == "CarePath API"
    assert "build" not in report
    assert calls == ["/health/live", "/health/ready", "/openapi.json"]


def test_exact_commit_verification_accepts_only_matching_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = "b" * 40

    def fake_fetch(base_url: str, path: str) -> dict[str, Any]:
        del base_url
        return _base_payload(path, commit=expected)

    monkeypatch.setattr(verify_backend, "fetch_json", fake_fetch)

    report = verify_backend.verify(
        "https://carepath.example",
        expected_commit=expected,
    )

    assert report["build"] == {"status": "ok", "git_commit": expected}


def test_exact_commit_verification_rejects_stale_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = "b" * 40

    def fake_fetch(base_url: str, path: str) -> dict[str, Any]:
        del base_url
        return _base_payload(path, commit="a" * 40)

    monkeypatch.setattr(verify_backend, "fetch_json", fake_fetch)

    with pytest.raises(RuntimeError, match="does not match expected commit"):
        verify_backend.verify(
            "https://carepath.example",
            expected_commit=expected,
        )


def test_exact_commit_verification_rejects_missing_build_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(base_url: str, path: str) -> dict[str, Any]:
        del base_url
        payload = _base_payload(path)
        if path == "/health/build":
            payload["git_commit"] = None
        return payload

    monkeypatch.setattr(verify_backend, "fetch_json", fake_fetch)

    with pytest.raises(RuntimeError, match="did not report a git commit"):
        verify_backend.verify(
            "https://carepath.example",
            expected_commit="a" * 40,
        )


def test_stable_verification_requires_consecutive_successes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str | None, int]] = []
    sleeps: list[float] = []

    def fake_verify(base_url: str, *, expected_commit: str | None = None) -> dict[str, Any]:
        assert base_url == "https://carepath.example"
        calls.append((expected_commit, len(calls) + 1))
        return {"base_url": base_url, "build": {"git_commit": expected_commit}}

    monkeypatch.setattr(verify_backend, "verify", fake_verify)

    report = verify_backend.verify_stable(
        "https://carepath.example",
        expected_commit="c" * 40,
        confirmations=3,
        confirmation_interval=2.5,
        sleep=sleeps.append,
    )

    assert report["confirmations"] == 3
    assert len(calls) == 3
    assert all(call[0] == "c" * 40 for call in calls)
    assert sleeps == [2.5, 2.5]


def test_stable_verification_rejects_invalid_confirmation_settings() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        verify_backend.verify_stable("https://carepath.example", confirmations=0)
    with pytest.raises(ValueError, match="cannot be negative"):
        verify_backend.verify_stable(
            "https://carepath.example",
            confirmation_interval=-0.1,
        )


@pytest.mark.parametrize(
    "workflow_path",
    (
        ".github/workflows/cp019-public-deployment.yml",
        ".github/workflows/cp020-reviewer-client.yml",
        ".github/workflows/mobile-browser-e2e.yml",
    ),
)
def test_public_deployment_workflows_pin_main_e2e_to_exact_stable_commit(
    workflow_path: str,
) -> None:
    workflow = Path(workflow_path).read_text(encoding="utf-8")

    assert '--expected-commit "${GITHUB_SHA}"' in workflow
    assert "--confirmations 3" in workflow
    assert "--confirmation-interval 5" in workflow
