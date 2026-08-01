from __future__ import annotations

import json
from pathlib import Path

from backend.retrieval.guidelines.ingest import build_ingestion_report
from backend.retrieval.guidelines.models import FailureCode, stable_source_id
from backend.retrieval.guidelines.registry import load_registry_with_failures


def test_invalid_registry_entry_is_reported_without_dropping_valid_entry(tmp_path: Path) -> None:
    valid_url = "https://example.gov/valid-guidance"
    payload = {
        "sources": [
            {
                "source_id": stable_source_id(valid_url),
                "title": "Valid guidance",
                "organisation": "Example Public Health Agency",
                "canonical_url": valid_url,
                "published_at": None,
                "updated_at": None,
                "retrieved_at": "2026-07-29",
                "topics": ["sleep"],
                "language": "en",
                "document_type": "public_health_guidance",
                "authority_type": "government",
                "license": "public domain",
                "redistribution_policy": "full_text_allowed",
                "full_text_storage_allowed": True,
                "notes": "Valid fixture.",
            },
            {
                "source_id": "src-bad-metadata",
                "title": "",
                "organisation": "Example Public Health Agency",
                "canonical_url": "https://example.gov/bad-guidance",
                "retrieved_at": "2026-07-29",
                "topics": ["sleep"],
                "language": "en",
                "document_type": "public_health_guidance",
                "authority_type": "government",
                "license": "unknown",
                "redistribution_policy": "unknown",
                "full_text_storage_allowed": False,
                "notes": "Invalid because the title and stable ID are not valid.",
            },
        ]
    }
    registry_path = tmp_path / "sources.yaml"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    sources, failures = load_registry_with_failures(registry_path)

    assert [source.source_id for source in sources] == [stable_source_id(valid_url)]
    assert len(failures) == 1
    assert failures[0].source_id == "src-bad-metadata"
    assert failures[0].code is FailureCode.INVALID_METADATA
    assert failures[0].reason

    report = build_ingestion_report((), metadata_failures=failures)
    item = report["sources"][0]  # type: ignore[index]
    assert item["source_id"] == "src-bad-metadata"  # type: ignore[index]
    assert item["status"] == "failed"  # type: ignore[index]
    assert item["failure_code"] == "invalid_metadata"  # type: ignore[index]
    assert item["chunk_count"] == 0  # type: ignore[index]
