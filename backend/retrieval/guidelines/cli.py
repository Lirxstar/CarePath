"""Command-line entrypoint for rebuilding the CP-006 derived evidence corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_chunks
from .ingest import fetch_error_result, ingest_document, write_corpus
from .models import (
    FailureCode,
    IngestionFailure,
    IngestionResult,
    RedistributionPolicy,
    SourceFormat,
)
from .registry import load_registry_with_failures

_INPUT_SUFFIXES: tuple[tuple[str, SourceFormat], ...] = (
    (".pdf.txt", SourceFormat.PDF_TEXT),
    (".html", SourceFormat.HTML),
    (".md", SourceFormat.MARKDOWN),
    (".txt", SourceFormat.TEXT),
)


def build_from_directory(
    registry_path: Path,
    inputs_dir: Path,
) -> tuple[tuple[IngestionResult, ...], tuple[IngestionFailure, ...]]:
    sources, metadata_failures = load_registry_with_failures(registry_path)
    results: list[IngestionResult] = []
    for source in sources:
        if source.redistribution_policy in {
            RedistributionPolicy.METADATA_ONLY,
            RedistributionPolicy.UNKNOWN,
        }:
            results.append(ingest_document(source, "", SourceFormat.TEXT))
            continue
        input_match = _find_input(inputs_dir, source.source_id)
        if input_match is None:
            results.append(
                fetch_error_result(source, "no local permitted source input was provided")
            )
            continue
        path, source_format = input_match
        results.append(
            ingest_document(
                source,
                path.read_text(encoding="utf-8"),
                source_format,
            )
        )
    return tuple(results), metadata_failures


def _find_input(inputs_dir: Path, source_id: str) -> tuple[Path, SourceFormat] | None:
    for suffix, source_format in _INPUT_SUFFIXES:
        candidate = inputs_dir / f"{source_id}{suffix}"
        if candidate.is_file():
            return candidate, source_format
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic CP-006 evidence corpus")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/guidelines/sources.yaml"),
    )
    parser.add_argument(
        "--inputs-dir",
        type=Path,
        default=Path("data/guidelines/inputs"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/guidelines/generated"),
    )
    args = parser.parse_args()

    results, metadata_failures = build_from_directory(args.registry, args.inputs_dir)
    write_corpus(args.output_dir, results, metadata_failures=metadata_failures)
    chunks = [chunk for result in results for chunk in result.chunks]
    if len(chunks) >= 30:
        report = audit_chunks(chunks, sample_size=30)
        (args.output_dir / "chunk_audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    unexpected_failures = [
        result.failure
        for result in results
        if result.failure is not None and result.failure.code is not FailureCode.LICENSE_RESTRICTED
    ]
    return 1 if metadata_failures or unexpected_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
