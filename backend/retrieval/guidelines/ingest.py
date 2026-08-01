"""Reproducible CP-006 ingestion, deduplication, reporting, and manifests."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from .chunker import chunk_sections
from .models import (
    CHUNKER_VERSION,
    CLEANER_VERSION,
    INGESTION_VERSION,
    PARSER_VERSION,
    ChunkConfig,
    FailureCode,
    GuidelineSource,
    GuidelineTopic,
    IngestionFailure,
    IngestionResult,
    RedistributionPolicy,
    Section,
    SourceFormat,
    SourceRegistryEntry,
    normalize_url,
    sha256_text,
)
from .parsers import parse_document
from .registry import load_registry_with_failures


def load_registry(path: Path) -> tuple[SourceRegistryEntry, ...]:
    """Load and strictly validate the canonical source registry."""

    sources, failures = load_registry_with_failures(path)
    if failures:
        failure_ids = ", ".join(failure.source_id for failure in failures)
        raise ValueError(f"source registry contains invalid metadata: {failure_ids}")
    validate_registry(sources)
    return sources


def validate_registry(sources: Sequence[SourceRegistryEntry]) -> None:
    if not 15 <= len(sources) <= 25:
        raise ValueError("source registry must contain between 15 and 25 sources")
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source_id values must be unique")
    canonical_urls = [normalize_url(source.canonical_url) for source in sources]
    if len(canonical_urls) != len(set(canonical_urls)):
        raise ValueError("canonical URLs must be unique after normalization")
    covered = {topic for source in sources for topic in source.topics}
    missing = set(GuidelineTopic) - covered
    if missing:
        missing_values = ", ".join(sorted(topic.value for topic in missing))
        raise ValueError(f"source registry is missing required topics: {missing_values}")


def _canonical_document_text(sections: Sequence[Section]) -> str:
    parts: list[str] = []
    for section in sections:
        heading = " / ".join(section.path)
        parts.append(f"{heading}\n{section.text}" if heading else section.text)
    return "\n\n".join(parts).strip()


def ingest_document(
    source_entry: SourceRegistryEntry,
    content: str,
    source_format: SourceFormat | str,
    *,
    config: ChunkConfig | None = None,
) -> IngestionResult:
    """Ingest one imported document without performing live network retrieval."""

    config = config or ChunkConfig()
    source = source_entry.to_domain()
    try:
        parsed_format = SourceFormat(source_format)
    except ValueError:
        return _failure(source, FailureCode.UNSUPPORTED_FORMAT, str(source_format))

    if source.redistribution_policy in {
        RedistributionPolicy.METADATA_ONLY,
        RedistributionPolicy.UNKNOWN,
    }:
        return _failure(
            source,
            FailureCode.LICENSE_RESTRICTED,
            f"redistribution_policy={source.redistribution_policy.value}",
        )
    if not content.strip():
        return _failure(source, FailureCode.EMPTY_CONTENT, "input content is empty")

    try:
        sections = parse_document(content, parsed_format)
    except (TypeError, ValueError) as exc:
        return _failure(source, FailureCode.PARSE_ERROR, str(exc))
    canonical_text = _canonical_document_text(sections)
    if not canonical_text:
        return _failure(source, FailureCode.EMPTY_CONTENT, "no usable content after parsing")

    source_hash = sha256_text(canonical_text)
    enriched_source = source.model_copy(update={"source_content_hash": source_hash})
    chunks = tuple(chunk_sections(sections, source=enriched_source, config=config))
    if not chunks:
        return _failure(enriched_source, FailureCode.EMPTY_CONTENT, "no chunks were generated")
    return IngestionResult(
        source=enriched_source,
        source_content_hash=source_hash,
        chunks=chunks,
    )


def fetch_error_result(source_entry: SourceRegistryEntry, reason: str) -> IngestionResult:
    return _failure(source_entry.to_domain(), FailureCode.FETCH_ERROR, reason)


def ingest_batch(
    documents: Sequence[tuple[SourceRegistryEntry, str, SourceFormat | str]],
    *,
    config: ChunkConfig | None = None,
) -> tuple[IngestionResult, ...]:
    """Ingest a batch while preserving source order and reporting duplicates."""

    config = config or ChunkConfig()
    config.validate()
    seen_source_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    results: list[IngestionResult] = []

    for source_entry, content, source_format in documents:
        if source_entry.source_id in seen_source_ids:
            results.append(
                _duplicate(source_entry.to_domain(), source_entry.source_id, "source_id")
            )
            continue
        result = ingest_document(source_entry, content, source_format, config=config)
        if result.failure is not None:
            results.append(result)
            seen_source_ids.add(source_entry.source_id)
            continue
        source_hash = result.source_content_hash
        if source_hash is not None and source_hash in seen_hashes:
            results.append(
                _duplicate(result.source, seen_hashes[source_hash], "source_content_hash")
            )
            seen_source_ids.add(source_entry.source_id)
            continue
        seen_source_ids.add(source_entry.source_id)
        if source_hash is not None:
            seen_hashes[source_hash] = source_entry.source_id
        results.append(result)
    return tuple(results)


def build_ingestion_report(
    results: Sequence[IngestionResult],
    *,
    metadata_failures: Sequence[IngestionFailure] = (),
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for metadata_failure in metadata_failures:
        items.append(
            {
                "source_id": metadata_failure.source_id,
                "status": "failed",
                "failure_code": metadata_failure.code.value,
                "reason": metadata_failure.reason,
                "duplicate_of": None,
                "chunk_count": 0,
                "source_content_hash": None,
            }
        )
    for result in results:
        result_failure = result.failure
        if result_failure is None:
            status = "ok"
        elif result_failure.code is FailureCode.LICENSE_RESTRICTED:
            status = "restricted"
        elif result_failure.code is FailureCode.DUPLICATE:
            status = "duplicate"
        else:
            status = "failed"
        items.append(
            {
                "source_id": result.source.source_id,
                "status": status,
                "failure_code": result_failure.code.value if result_failure else None,
                "reason": result_failure.reason if result_failure else None,
                "duplicate_of": result.duplicate_of,
                "chunk_count": len(result.chunks),
                "source_content_hash": result.source_content_hash,
            }
        )
    return {"ingestion_version": INGESTION_VERSION, "sources": items}


def build_manifest(
    results: Sequence[IngestionResult],
    *,
    config: ChunkConfig | None = None,
    invalid_source_count: int = 0,
) -> dict[str, object]:
    """Build deterministic manifest content; runtime timestamps are intentionally excluded."""

    config = config or ChunkConfig()
    config.validate()
    policies = Counter(result.source.redistribution_policy.value for result in results)
    chunks = [chunk for result in results for chunk in result.chunks]
    return {
        "ingestion_version": INGESTION_VERSION,
        "parser_version": PARSER_VERSION,
        "cleaner_version": CLEANER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "source_count": len(results),
        "invalid_source_count": invalid_source_count,
        "chunk_count": len(chunks),
        "configuration": {
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "minimum_chunk_size": config.minimum_chunk_size,
        },
        "source_ids": [result.source.source_id for result in results],
        "source_hashes": {
            result.source.source_id: result.source_content_hash for result in results
        },
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "license_policy_summary": dict(sorted(policies.items())),
    }


def dump_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_corpus(
    output_dir: Path,
    results: Sequence[IngestionResult],
    *,
    config: ChunkConfig | None = None,
    metadata_failures: Sequence[IngestionFailure] = (),
) -> None:
    """Write derived chunks, a deterministic manifest, and a structured report."""

    config = config or ChunkConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = [chunk for result in results for chunk in result.chunks]
    chunk_lines = [json.dumps(chunk.model_dump(mode="json"), sort_keys=True) for chunk in chunks]
    serialized_chunks = "\n".join(chunk_lines) + ("\n" if chunk_lines else "")
    (output_dir / "chunks.jsonl").write_text(serialized_chunks, encoding="utf-8")
    (output_dir / "corpus_manifest.json").write_text(
        dump_json(
            build_manifest(
                results,
                config=config,
                invalid_source_count=len(metadata_failures),
            )
        ),
        encoding="utf-8",
    )
    (output_dir / "ingestion_report.json").write_text(
        dump_json(build_ingestion_report(results, metadata_failures=metadata_failures)),
        encoding="utf-8",
    )


def _failure(source: GuidelineSource, code: FailureCode, reason: str) -> IngestionResult:
    return IngestionResult(
        source=source,
        source_content_hash=source.source_content_hash,
        chunks=(),
        failure=IngestionFailure(source.source_id, code, reason),
    )


def _duplicate(source: GuidelineSource, duplicate_of: str, basis: str) -> IngestionResult:
    return IngestionResult(
        source=source,
        source_content_hash=None,
        chunks=(),
        failure=IngestionFailure(source.source_id, FailureCode.DUPLICATE, f"duplicate {basis}"),
        duplicate_of=duplicate_of,
    )
