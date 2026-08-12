"""Fetch, build, and serialise the CP-201 Tokyo resource corpus."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import httpx

from backend.tokyo.ingest import ingest_source, merge_duplicates
from backend.tokyo.models import SourceBuildResult, SourceRegistry, TokyoBuildReport, TokyoResource
from backend.tokyo.registry import resolve_download_url


def fetch_payloads(
    registry: SourceRegistry,
    *,
    client: httpx.Client,
    raw_dir: Path | None = None,
) -> tuple[dict[str, bytes], dict[str, str]]:
    payloads: dict[str, bytes] = {}
    urls: dict[str, str] = {}
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
    for source in registry.sources:
        url = resolve_download_url(source, client)
        response = client.get(url, timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        payload = response.content
        if not payload:
            raise ValueError(f"empty payload from {source.source_id}")
        payloads[source.source_id] = payload
        urls[source.source_id] = url
        if raw_dir is not None:
            extension = ".zip" if source.format.value == "zip_csv" else ".csv"
            (raw_dir / f"{source.source_id}{extension}").write_bytes(payload)
    return payloads, urls


def build_resources(
    registry: SourceRegistry,
    payloads: Mapping[str, bytes],
    resolved_urls: Mapping[str, str],
) -> tuple[list[TokyoResource], TokyoBuildReport]:
    resources: list[TokyoResource] = []
    results: list[SourceBuildResult] = []
    for source in registry.sources:
        payload = payloads.get(source.source_id)
        resolved_url = resolved_urls.get(source.source_id)
        if payload is None or resolved_url is None:
            results.append(SourceBuildResult(source_id=source.source_id, error="payload missing"))
            continue
        try:
            source_resources, result = ingest_source(source, payload, resolved_url)
        except (ValueError, OSError) as exc:
            results.append(SourceBuildResult(source_id=source.source_id, error=str(exc)))
            continue
        resources.extend(source_resources)
        results.append(result)
    merged, duplicates = merge_duplicates(resources)
    report = TokyoBuildReport(
        resources=len(merged),
        duplicates_merged=duplicates,
        source_results=results,
    )
    return merged, report


def write_artifacts(
    resources: list[TokyoResource],
    report: TokyoBuildReport,
    *,
    output_path: Path,
    report_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(resource.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for resource in sorted(resources, key=lambda item: item.resource_id)
    ]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
