"""Registry loading and CKAN resolution for CP-201 Tokyo datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx

from backend.tokyo.models import SourceRegistry, SourceRegistryEntry

TOKYO_CKAN_PACKAGE_SHOW = "https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_show"


def load_registry(path: Path) -> SourceRegistry:
    return SourceRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_download_url(source: SourceRegistryEntry, client: httpx.Client) -> str:
    if source.download_url is not None:
        return source.download_url
    assert source.ckan_dataset_id is not None
    assert source.ckan_resource_name is not None
    response = client.get(
        TOKYO_CKAN_PACKAGE_SHOW,
        params={"id": source.ckan_dataset_id},
        timeout=30.0,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    if not payload.get("success"):
        raise ValueError(f"CKAN package lookup failed for {source.source_id}")
    result = cast(dict[str, Any], payload.get("result", {}))
    resources = cast(list[dict[str, Any]], result.get("resources", []))
    wanted = _normalized_resource_name(source.ckan_resource_name)
    matches = [
        resource
        for resource in resources
        if _normalized_resource_name(str(resource.get("name", ""))) == wanted
        and str(resource.get("format", "")).upper() == "CSV"
    ]
    if len(matches) != 1:
        available = sorted(str(resource.get("name", "")) for resource in resources)
        raise ValueError(
            f"expected one CSV resource named {source.ckan_resource_name!r}; "
            f"found {len(matches)}; available={json.dumps(available, ensure_ascii=False)}"
        )
    url = str(matches[0].get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"CKAN resource for {source.source_id} has no absolute URL")
    return url


def _normalized_resource_name(value: str) -> str:
    value = value.strip()
    if value.upper().endswith("CSV"):
        value = value[:-3]
    return value.strip().replace("　", " ")
