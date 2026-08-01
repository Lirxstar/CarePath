"""Tolerant CP-006 source-registry loading with per-source metadata failures."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import FailureCode, IngestionFailure, SourceRegistryEntry


def load_registry_with_failures(
    path: Path,
) -> tuple[tuple[SourceRegistryEntry, ...], tuple[IngestionFailure, ...]]:
    """Load valid entries while preserving invalid source failures for batch reporting."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load source registry: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("source registry must contain a sources list")

    sources: list[SourceRegistryEntry] = []
    failures: list[IngestionFailure] = []
    for index, raw_source in enumerate(payload["sources"]):
        fallback_id = _fallback_source_id(raw_source, index)
        try:
            sources.append(SourceRegistryEntry.model_validate(raw_source))
        except ValidationError as exc:
            failures.append(
                IngestionFailure(
                    source_id=fallback_id,
                    code=FailureCode.INVALID_METADATA,
                    reason=_validation_reason(exc),
                )
            )
    return tuple(sources), tuple(failures)


def _fallback_source_id(raw_source: object, index: int) -> str:
    if isinstance(raw_source, dict):
        value = raw_source.get("source_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"registry-index-{index}"


def _validation_reason(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else None
    if first is None:
        return "invalid source metadata"
    location = ".".join(str(item) for item in first.get("loc", ())) or "source"
    message = str(first.get("msg", "invalid metadata"))
    return f"{location}: {message}"
