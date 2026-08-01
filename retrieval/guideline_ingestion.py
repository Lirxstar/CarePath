"""Auditable guideline ingestion primitives using canonical KnowledgeChunk."""

import re
from collections.abc import Mapping
from hashlib import sha256

from backend.domain import KnowledgeChunk

_BLOCKED_INGESTION_STATUSES = {
    "metadata_only_pending_ai_permission",
    "metadata_only_pending_permission",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _source_id(source: Mapping[str, object]) -> str:
    value = source.get("source_id", source.get("id"))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source must contain a non-empty source_id or id")
    return value.strip()


def _section_title(source: Mapping[str, object]) -> str | None:
    value = source.get("section_title")
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def chunk_text(
    text: str,
    source: Mapping[str, object],
    size: int = 800,
    overlap: int = 120,
    embedding_model: str = "not_yet_embedded",
) -> list[KnowledgeChunk]:
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    cleaned = clean_text(text)
    if not cleaned:
        return []

    source_id = _source_id(source)
    section_title = _section_title(source)
    chunks: list[KnowledgeChunk] = []
    start = 0
    index = 0

    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        content = cleaned[start:end].strip()
        if content:
            content_hash = sha256(content.encode()).hexdigest()
            chunk_hash = sha256(f"{source_id}:{index}:{content}".encode()).hexdigest()
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{source_id}-{chunk_hash[:16]}",
                    source_id=source_id,
                    section_title=section_title,
                    content=content,
                    embedding_model=embedding_model,
                    content_hash=content_hash,
                )
            )
        if end == len(cleaned):
            break
        start = end - overlap
        index += 1

    return chunks


def can_ingest(source: Mapping[str, object]) -> bool:
    return source.get("ingestion_status") not in _BLOCKED_INGESTION_STATUSES
