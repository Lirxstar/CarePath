from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def fetch_json(base_url: str, path: str) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "carepath-deployment-verifier/1"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"deployment check failed for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"deployment check returned non-object JSON for {path}")
    return payload


def verify(base_url: str) -> dict[str, Any]:
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

    return {
        "base_url": base_url.rstrip("/"),
        "liveness": live,
        "readiness": ready,
        "openapi_title": info["title"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a deployed CarePath backend.")
    parser.add_argument("base_url", help="Public backend origin, for example https://example.test")
    args = parser.parse_args()

    try:
        report = verify(args.base_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
