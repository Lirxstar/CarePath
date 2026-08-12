from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

Sleep = Callable[[float], None]


def fetch_json(base_url: str, path: str) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "carepath-deployment-verifier/2",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"deployment check failed for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"deployment check returned non-object JSON for {path}")
    return payload


def verify(base_url: str, *, expected_commit: str | None = None) -> dict[str, Any]:
    live = fetch_json(base_url, "/health/live")
    ready = fetch_json(base_url, "/health/ready")
    openapi = fetch_json(base_url, "/openapi.json")

    if live.get("status") != "ok":
        raise RuntimeError("liveness probe did not report ok")
    if ready.get("status") != "ready":
        raise RuntimeError("readiness probe did not report ready")
    info = openapi.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("title"), str):
        raise RuntimeError("OpenAPI document is missing service metadata")

    report: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "liveness": live,
        "readiness": ready,
        "openapi_title": info["title"],
    }

    if expected_commit is not None:
        build = fetch_json(base_url, "/health/build")
        deployed_commit = build.get("git_commit")
        if build.get("status") != "ok" or not isinstance(deployed_commit, str):
            raise RuntimeError("build identity probe did not report a git commit")
        if deployed_commit != expected_commit:
            raise RuntimeError(
                "deployed commit "
                f"{deployed_commit} does not match expected commit {expected_commit}"
            )
        report["build"] = build

    return report


def verify_stable(
    base_url: str,
    *,
    expected_commit: str | None = None,
    confirmations: int = 1,
    confirmation_interval: float = 5.0,
    sleep: Sleep = time.sleep,
) -> dict[str, Any]:
    """Require repeated healthy probes so a rolling deployment cannot pass on one transient hit."""

    if confirmations < 1:
        raise ValueError("confirmations must be at least 1")
    if confirmation_interval < 0:
        raise ValueError("confirmation interval cannot be negative")

    report: dict[str, Any] | None = None
    for confirmation in range(confirmations):
        report = verify(base_url, expected_commit=expected_commit)
        if confirmation + 1 < confirmations:
            sleep(confirmation_interval)

    if report is None:  # pragma: no cover - guarded by confirmations validation
        raise RuntimeError("deployment verification produced no report")
    report["confirmations"] = confirmations
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a deployed CarePath backend.")
    parser.add_argument("base_url", help="Public backend origin, for example https://example.test")
    parser.add_argument(
        "--expected-commit",
        help="Require /health/build to report this exact deployed git commit.",
    )
    parser.add_argument(
        "--confirmations",
        type=int,
        default=1,
        help="Number of consecutive successful probes required before returning success.",
    )
    parser.add_argument(
        "--confirmation-interval",
        type=float,
        default=5.0,
        help="Seconds between consecutive successful confirmation probes.",
    )
    args = parser.parse_args()

    try:
        report = verify_stable(
            args.base_url,
            expected_commit=args.expected_commit,
            confirmations=args.confirmations,
            confirmation_interval=args.confirmation_interval,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
