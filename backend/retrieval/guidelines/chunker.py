"""Section-aware, deterministic chunking for curated guideline evidence."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .cleaner import clean_text
from .models import (
    ChunkConfig,
    GuidelineChunk,
    GuidelineSource,
    Section,
    sha256_text,
    stable_chunk_id,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_words(text: str, limit: int) -> list[str]:
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        added = len(word) if not current else len(word) + 1
        if current and current_length + added > limit:
            pieces.append(" ".join(current))
            current = [word]
            current_length = len(word)
        else:
            current.append(word)
            current_length += added
    if current:
        pieces.append(" ".join(current))
    return pieces


def _split_long_unit(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    sentences = [item.strip() for item in _SENTENCE_SPLIT.split(text) if item.strip()]
    if len(sentences) <= 1:
        return _split_words(text, limit)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        sentence_parts = _split_words(sentence, limit) if len(sentence) > limit else [sentence]
        for part in sentence_parts:
            candidate = part if not current else f"{current} {part}"
            if current and len(candidate) > limit:
                pieces.append(current)
                current = part
            else:
                current = candidate
    if current:
        pieces.append(current)
    return pieces


def _semantic_tail(text: str, overlap: int, capacity: int) -> str:
    if overlap <= 0 or capacity <= 0:
        return ""
    budget = min(overlap, capacity, len(text))
    suffix = text[-budget:]
    first_space = suffix.find(" ")
    if first_space >= 0:
        suffix = suffix[first_space + 1 :]
    return suffix.strip()


def _section_units(section: Section, limit: int) -> Iterable[str]:
    for paragraph in clean_text(section.text).split("\n\n"):
        value = paragraph.strip()
        if value:
            yield from _split_long_unit(value, limit)


def _pack_section(section: Section, config: ChunkConfig) -> list[str]:
    units = list(_section_units(section, config.chunk_size))
    if not units:
        return []
    packed: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else f"{current}\n\n{unit}"
        if not current or len(candidate) <= config.chunk_size:
            current = candidate
            continue
        packed.append(current)
        capacity = config.chunk_size - len(unit) - 2
        tail = _semantic_tail(current, config.chunk_overlap, capacity)
        current = f"{tail}\n\n{unit}" if tail else unit
    if current:
        packed.append(current)

    if len(packed) >= 2 and len(packed[-1]) < config.minimum_chunk_size:
        merged = f"{packed[-2]}\n\n{packed[-1]}"
        if len(merged) <= config.chunk_size:
            packed[-2:] = [merged]
    return packed


def chunk_sections(
    sections: Sequence[Section],
    *,
    source: GuidelineSource,
    config: ChunkConfig | None = None,
) -> list[GuidelineChunk]:
    config = config or ChunkConfig()
    config.validate()
    if source.source_content_hash is None:
        raise ValueError("source_content_hash is required before chunking")

    chunks: list[GuidelineChunk] = []
    chunk_index = 0
    for section in sections:
        for content in _pack_section(section, config):
            digest = sha256_text(content)
            chunks.append(
                GuidelineChunk(
                    chunk_id=stable_chunk_id(source.source_id, section.path, chunk_index, digest),
                    source_id=source.source_id,
                    section_title=section.path[-1] if section.path else None,
                    content=content,
                    embedding_model="not_yet_embedded",
                    content_hash=digest,
                    title=source.title,
                    section_path=list(section.path),
                    canonical_url=source.canonical_url,
                    published_at=source.published_at,
                    updated_at=source.updated_at,
                    language=source.language,
                    topics=source.topics,
                    chunk_index=chunk_index,
                    license=source.license,
                    retrieved_at=source.retrieved_at,
                    source_content_hash=source.source_content_hash,
                )
            )
            chunk_index += 1
    return chunks
