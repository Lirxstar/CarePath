from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def fetch_json(base_url: str, path: str) -> dict[str, Any]:
    request = Request(
        _url(base_url, path),
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "carepath-cp208-verifier/1",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Tokyo deployment check failed for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Tokyo deployment check returned non-object JSON for {path}")
    return payload


def fetch_html(base_url: str, path: str) -> str:
    request = Request(
        _url(base_url, path),
        headers={
            "Accept": "text/html",
            "Cache-Control": "no-cache",
            "User-Agent": "carepath-cp208-verifier/1",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Tokyo public route check failed for {path}") from exc
    if "text/html" not in content_type.lower() or "<html" not in body.lower():
        raise RuntimeError("public /tokyo route did not return an HTML document")
    return body


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        _url(base_url, path),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "carepath-cp208-verifier/1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Tokyo public search failed for {path}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"Tokyo public search returned non-object JSON for {path}")
    return body


def verify(base_url: str, *, expected_commit: str | None = None) -> dict[str, Any]:
    live = fetch_json(base_url, "/health/live")
    tokyo = fetch_json(base_url, "/health/tokyo")
    html = fetch_html(base_url, "/tokyo")

    if live.get("status") != "ok":
        raise RuntimeError("liveness probe did not report ok")
    if tokyo.get("status") != "ready":
        raise RuntimeError("Tokyo readiness probe did not report ready")
    checks = tokyo.get("checks")
    if not isinstance(checks, dict) or checks.get("resource_data") != "ok":
        raise RuntimeError("Tokyo readiness did not confirm source-backed resource data")
    if checks.get("provider") not in {"ok", "fallback"}:
        raise RuntimeError("Tokyo readiness returned an invalid provider state")
    resource_count = tokyo.get("resource_count")
    if not isinstance(resource_count, int) or resource_count <= 0:
        raise RuntimeError("Tokyo readiness reported an empty resource corpus")
    if tokyo.get("deterministic_search_available") is not True:
        raise RuntimeError("Tokyo deterministic search is not available")

    search = post_json(
        base_url,
        "/tokyo/agent/search",
        {
            "query": (
                "It is extremely hot. I need a nearby designated place where I can cool down."
            ),
            "interface_language": "en",
            "location": {"mode": "municipality", "municipality": "江東区"},
            "radius_km": 10,
            "limit": 5,
        },
    )
    if search.get("status") != "ok":
        raise RuntimeError("public Tokyo demo search did not return status=ok")
    search_payload = search.get("search")
    if not isinstance(search_payload, dict):
        raise RuntimeError("public Tokyo demo search did not return a search result object")
    results = search_payload.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("public Tokyo demo search returned no source-backed resources")

    resource_ids: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            raise RuntimeError("public Tokyo search result was not an object")
        resource = item.get("resource")
        if not isinstance(resource, dict):
            raise RuntimeError("public Tokyo result did not contain a resource object")
        resource_id = resource.get("resource_id")
        provenance = resource.get("provenance")
        if not isinstance(resource_id, str) or not resource_id:
            raise RuntimeError("public Tokyo result lacked a stable resource ID")
        if not isinstance(provenance, list) or not provenance:
            raise RuntimeError(f"public Tokyo resource {resource_id} lacked provenance")
        for source in provenance:
            if not isinstance(source, dict) or not source.get("source_url"):
                raise RuntimeError(f"public Tokyo resource {resource_id} had incomplete provenance")
        resource_ids.append(resource_id)

    report: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "liveness": live,
        "tokyo_readiness": tokyo,
        "tokyo_route_html_bytes": len(html.encode("utf-8")),
        "demo_query": {
            "language": "en",
            "location_mode": "municipality",
            "municipality": "江東区",
            "status": search["status"],
            "resource_ids": resource_ids,
            "provider_status": search.get("explanation_model_status"),
        },
    }

    if expected_commit is not None:
        build = fetch_json(base_url, "/health/build")
        deployed_commit = build.get("git_commit")
        if build.get("status") != "ok" or not isinstance(deployed_commit, str):
            raise RuntimeError("build identity probe did not report a git commit")
        if deployed_commit != expected_commit:
            raise RuntimeError(
                f"deployed commit {deployed_commit} does not match expected commit {expected_commit}"
            )
        report["build"] = build

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the public CP-208 CarePath Tokyo deployment and grounded demo path."
    )
    parser.add_argument("base_url", help="Public CarePath origin, for example https://example.test")
    parser.add_argument(
        "--expected-commit",
        help="Require /health/build to report this exact deployed git commit.",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional path for the machine-readable verification report.",
    )
    args = parser.parse_args()

    try:
        report = verify(args.base_url, expected_commit=args.expected_commit)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        from pathlib import Path

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
