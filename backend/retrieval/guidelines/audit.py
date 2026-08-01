"""Deterministic quality audit helpers for CP-006 evidence chunks."""

from __future__ import annotations

from collections.abc import Sequence

from .cleaner import is_boilerplate_line
from .models import GuidelineChunk


def audit_chunks(
    chunks: Sequence[GuidelineChunk],
    *,
    sample_size: int = 30,
) -> dict[str, object]:
    """Audit a deterministic cross-source sample and return reviewer-readable checks."""

    if sample_size < 30:
        raise ValueError("CP-006 audit sample_size must be at least 30")
    if len(chunks) < sample_size:
        raise ValueError("not enough chunks for the requested CP-006 audit")

    ordered = sorted(chunks, key=lambda chunk: (chunk.source_id, chunk.chunk_index, chunk.chunk_id))
    step = max(1, len(ordered) // sample_size)
    sample = ordered[::step][:sample_size]
    items: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for chunk in sample:
        lines = [line.strip() for line in chunk.content.splitlines() if line.strip()]
        noise = [line for line in lines if is_boilerplate_line(line)]
        duplicate = chunk.chunk_id in seen_ids
        seen_ids.add(chunk.chunk_id)
        items.append(
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "title": chunk.title,
                "section_title": chunk.section_title,
                "canonical_url": chunk.canonical_url,
                "updated_at": chunk.updated_at.isoformat() if chunk.updated_at else None,
                "content_hash": chunk.content_hash,
                "source_content_hash": chunk.source_content_hash,
                "content_present": bool(chunk.content.strip()),
                "navigation_noise": noise,
                "duplicate_chunk_id": duplicate,
            }
        )

    return {
        "sample_size": len(sample),
        "distinct_sources": len({chunk.source_id for chunk in sample}),
        "distinct_topics": sorted({topic.value for chunk in sample for topic in chunk.topics}),
        "all_content_present": all(item["content_present"] for item in items),
        "navigation_noise_count": sum(bool(item["navigation_noise"]) for item in items),
        "duplicate_chunk_id_count": sum(bool(item["duplicate_chunk_id"]) for item in items),
        "items": items,
    }
