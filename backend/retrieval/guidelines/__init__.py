"""Curated external guideline ingestion for CP-006."""

from .ingest import (
    build_ingestion_report,
    build_manifest,
    ingest_batch,
    ingest_document,
    load_registry,
)
from .models import (
    ChunkConfig,
    FailureCode,
    GuidelineChunk,
    GuidelineSource,
    IngestionFailure,
    IngestionResult,
    RedistributionPolicy,
    SourceFormat,
    SourceRegistryEntry,
)
from .registry import load_registry_with_failures

__all__ = [
    "ChunkConfig",
    "FailureCode",
    "GuidelineChunk",
    "GuidelineSource",
    "IngestionFailure",
    "IngestionResult",
    "RedistributionPolicy",
    "SourceFormat",
    "SourceRegistryEntry",
    "build_ingestion_report",
    "build_manifest",
    "ingest_batch",
    "ingest_document",
    "load_registry",
    "load_registry_with_failures",
]
