"""Small source-backed evidence index for reliable public deployments.

The research/local path continues to prefer the CP-007 Qdrant vector index when a
built collection is available. This module provides a deterministic fallback for
public deployments that intentionally do not ship the large generated Qdrant
artifact or embedding model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import Language
from backend.retrieval.guidelines.models import GuidelineTopic

from .vector import (
    ExternalEvidenceFilters,
    ExternalEvidenceHit,
    ExternalEvidenceMetadata,
    display_citation,
)

_BUNDLE_INDEX_VERSION = "public-evidence-bundle-v1"
_BUNDLE_RETRIEVAL_MODEL = "carepath-deterministic-lexical-v1"
_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]|[\u3040-\u30ff]+")


class BundledEvidenceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section_title: str | None = None
    canonical_url: str = Field(min_length=1)
    published_at: date | None = None
    updated_at: date | None = None
    retrieved_at: date
    language: Language
    topics: tuple[GuidelineTopic, ...] = Field(min_length=1)
    organisation: str = Field(min_length=1)
    license: str = Field(min_length=1)
    content: str = Field(min_length=1)
    keywords: tuple[str, ...] = ()


class BundledEvidenceCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str = Field(min_length=1)
    retrieved_at: date
    entries: tuple[BundledEvidenceEntry, ...] = Field(min_length=1)


class BundledExternalEvidenceIndex:
    """Deterministic lexical search over a small reviewed public evidence bundle."""

    def __init__(self, corpus: BundledEvidenceCorpus) -> None:
        chunk_ids = [entry.chunk_id for entry in corpus.entries]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("public evidence bundle contains duplicate chunk_id values")
        self.corpus = corpus

    @classmethod
    def from_path(cls, path: Path) -> BundledExternalEvidenceIndex:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"unable to read public evidence bundle: {path}") from exc
        return cls(BundledEvidenceCorpus.model_validate(raw))

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: ExternalEvidenceFilters | None = None,
    ) -> tuple[ExternalEvidenceHit, ...]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= 50:
            raise ValueError("top_k must be between 1 and 50")

        active_filters = filters or ExternalEvidenceFilters()
        query_tokens = _tokens(query)
        ranked: list[tuple[float, BundledEvidenceEntry]] = []
        for entry in self.corpus.entries:
            if not _matches_filters(entry, active_filters):
                continue
            score = _lexical_score(query_tokens, entry)
            if score > 0:
                ranked.append((score, entry))

        ranked.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(_hit(entry, score) for score, entry in ranked[:top_k])


def _tokens(text: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_RE.findall(text))


def _lexical_score(query_tokens: frozenset[str], entry: BundledEvidenceEntry) -> float:
    if not query_tokens:
        return 0.0
    content_tokens = _tokens(entry.content)
    keyword_tokens = _tokens(" ".join(entry.keywords))
    content_overlap = len(query_tokens & content_tokens)
    keyword_overlap = len(query_tokens & keyword_tokens)
    if content_overlap == 0 and keyword_overlap == 0:
        return 0.0
    denominator = math.sqrt(len(query_tokens) * max(1, len(content_tokens | keyword_tokens)))
    return min(1.0, (content_overlap + 2.0 * keyword_overlap) / max(1.0, denominator))


def _matches_filters(entry: BundledEvidenceEntry, filters: ExternalEvidenceFilters) -> bool:
    if filters.topics and not set(filters.topics).intersection(entry.topics):
        return False
    if filters.language is not None and entry.language != filters.language:
        return False
    if filters.organisation is not None:
        expected = " ".join(filters.organisation.casefold().split())
        actual = " ".join(entry.organisation.casefold().split())
        if actual != expected:
            return False
    if filters.updated_from is not None and (
        entry.updated_at is None or entry.updated_at < filters.updated_from
    ):
        return False
    return not (
        filters.updated_to is not None
        and (entry.updated_at is None or entry.updated_at > filters.updated_to)
    )


def _hit(entry: BundledEvidenceEntry, score: float) -> ExternalEvidenceHit:
    content_hash = hashlib.sha256(entry.content.encode("utf-8")).hexdigest()
    source_snapshot = "|".join(
        (
            entry.source_id,
            entry.updated_at.isoformat() if entry.updated_at is not None else "unknown",
            entry.retrieved_at.isoformat(),
            entry.content,
        )
    )
    metadata = ExternalEvidenceMetadata(
        chunk_id=entry.chunk_id,
        source_id=entry.source_id,
        title=entry.title,
        section_title=entry.section_title,
        section_path=((entry.section_title,) if entry.section_title is not None else ()),
        canonical_url=entry.canonical_url,
        published_at=entry.published_at,
        updated_at=entry.updated_at,
        retrieved_at=entry.retrieved_at,
        language=entry.language,
        topics=entry.topics,
        organisation=entry.organisation,
        license=entry.license,
        source_content_hash=hashlib.sha256(source_snapshot.encode("utf-8")).hexdigest(),
        content_hash=content_hash,
        ingestion_version=_BUNDLE_INDEX_VERSION,
        index_version=_BUNDLE_INDEX_VERSION,
        embedding_model=_BUNDLE_RETRIEVAL_MODEL,
    )
    return ExternalEvidenceHit(
        chunk_id=entry.chunk_id,
        score=score,
        content=entry.content,
        metadata=metadata,
        citation=display_citation(metadata),
    )
