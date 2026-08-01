"""Qdrant-backed external guideline retrieval with stable citations and filters."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid5

from fastembed import TextEmbedding
from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient, models

from backend.domain.models import Language
from backend.retrieval.guidelines.models import GuidelineChunk, GuidelineTopic, SourceRegistryEntry
from backend.retrieval.guidelines.registry import load_registry_with_failures

INDEX_VERSION = "cp007-vector-v1"
DEFAULT_COLLECTION_NAME = "carepath_guidelines_cp007_v1"
DEFAULT_MULTILINGUAL_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_VECTOR_SIZE = 384
_POINT_NAMESPACE = UUID("06b46759-80bc-4f3c-ae94-f7674e06c9fd")
_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]|[\u3040-\u30ff]+")

COLLECTION_SCHEMA: dict[str, object] = {
    "index_version": INDEX_VERSION,
    "distance": "cosine",
    "payload_fields": {
        "chunk_id": "keyword",
        "source_id": "keyword",
        "topics": "keyword[]",
        "language": "keyword",
        "organisation": "keyword",
        "organisation_key": "keyword",
        "updated_at": "date|null",
        "updated_ordinal": "integer|null",
        "canonical_url": "keyword",
    },
}


class EmbeddingModel(Protocol):
    """Embedding seam so CI can use a deterministic model without downloading weights."""

    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedMultilingualModel:
    """Lazy FastEmbed wrapper for the configured multilingual production model."""

    def __init__(
        self,
        model_name: str = DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
        *,
        dimension: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self._name = model_name.strip()
        self._dimension = dimension
        self._model: TextEmbedding | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(model_name=self._name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._load()
        embed = model.embed
        vectors = [list(map(float, vector)) for vector in embed(list(texts))]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"embedding model {self.name} returned dimension {len(vector)}, "
                    f"expected {self.dimension}"
                )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("query must not be empty")
        vectors = self.embed_documents([text])
        return vectors[0]


class DeterministicHashEmbeddingModel:
    """Small deterministic test embedding; never used as the production default."""

    def __init__(self, dimension: int = 96) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self._dimension = dimension

    @property
    def name(self) -> str:
        return "carepath-deterministic-hash-v1"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("query must not be empty")
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        tokens = tuple(token.casefold() for token in _TOKEN_RE.findall(text))
        if not tokens:
            return [0.0] * self.dimension
        frequencies = Counter(tokens)
        values = [0.0] * self.dimension
        for token, count in frequencies.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(item * item for item in values))
        if norm == 0:
            return values
        return [item / norm for item in values]


class ExternalEvidenceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topics: tuple[GuidelineTopic, ...] = ()
    language: Language | None = None
    organisation: str | None = None
    updated_from: date | None = None
    updated_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> ExternalEvidenceFilters:
        if self.updated_from and self.updated_to and self.updated_to < self.updated_from:
            raise ValueError("updated_to must not be before updated_from")
        return self


class ExternalEvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    source_id: str
    title: str
    section_title: str | None = None
    section_path: tuple[str, ...] = ()
    canonical_url: str
    published_at: date | None = None
    updated_at: date | None = None
    retrieved_at: date
    language: Language
    topics: tuple[GuidelineTopic, ...]
    organisation: str
    license: str
    source_content_hash: str
    content_hash: str
    ingestion_version: str
    index_version: str = INDEX_VERSION
    embedding_model: str


class ExternalEvidenceHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    score: float
    content: str
    metadata: ExternalEvidenceMetadata
    citation: str


class IndexBuildReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_name: str
    index_version: str
    embedding_model: str
    vector_size: int
    source_count: int
    chunk_count: int


class ExternalRecallCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    relevant_chunk_ids: frozenset[str] = Field(min_length=1)
    filters: ExternalEvidenceFilters = Field(default_factory=ExternalEvidenceFilters)


@dataclass(frozen=True)
class IndexedSource:
    entry: SourceRegistryEntry

    @property
    def organisation_key(self) -> str:
        return " ".join(self.entry.organisation.casefold().split())


class QdrantExternalEvidenceIndex:
    """Versioned external-evidence index backed by Qdrant local or server clients."""

    def __init__(
        self,
        client: QdrantClient,
        embedder: EmbeddingModel,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name must not be empty")
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name.strip()

    def rebuild(
        self,
        chunks: Sequence[GuidelineChunk],
        sources: Sequence[SourceRegistryEntry],
    ) -> IndexBuildReport:
        if not chunks:
            raise ValueError("at least one guideline chunk is required")
        source_map = {item.source_id: IndexedSource(item) for item in sources}
        if len(source_map) != len(sources):
            raise ValueError("duplicate source_id in source registry")
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("duplicate chunk_id in guideline corpus")
        missing_sources = sorted({chunk.source_id for chunk in chunks} - set(source_map))
        if missing_sources:
            raise ValueError(f"chunks reference unknown sources: {', '.join(missing_sources)}")

        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.embedder.dimension,
                distance=models.Distance.COSINE,
            ),
        )

        vectors = self.embedder.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding model returned the wrong number of vectors")
        points: list[models.PointStruct] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            source = source_map[chunk.source_id]
            metadata = self._metadata(chunk, source.entry)
            citation = display_citation(metadata)
            payload = {
                **metadata.model_dump(mode="json"),
                "content": chunk.content,
                "citation": citation,
                "organisation_key": source.organisation_key,
                "updated_ordinal": chunk.updated_at.toordinal() if chunk.updated_at else None,
            }
            points.append(
                models.PointStruct(
                    id=str(uuid5(_POINT_NAMESPACE, chunk.chunk_id)),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        return IndexBuildReport(
            collection_name=self.collection_name,
            index_version=INDEX_VERSION,
            embedding_model=self.embedder.name,
            vector_size=self.embedder.dimension,
            source_count=len({chunk.source_id for chunk in chunks}),
            chunk_count=len(chunks),
        )

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
        if not self.client.collection_exists(self.collection_name):
            raise ValueError(f"Qdrant collection does not exist: {self.collection_name}")
        query_filter = _qdrant_filter(filters or ExternalEvidenceFilters())
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedder.embed_query(query),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        hits: list[ExternalEvidenceHit] = []
        for point in response.points:
            payload = point.payload or {}
            metadata = ExternalEvidenceMetadata.model_validate(_metadata_payload(payload))
            content = payload.get("content")
            citation = payload.get("citation")
            if not isinstance(content, str) or not isinstance(citation, str):
                raise ValueError("indexed point is missing content or citation")
            hits.append(
                ExternalEvidenceHit(
                    chunk_id=metadata.chunk_id,
                    score=float(point.score),
                    content=content,
                    metadata=metadata,
                    citation=citation,
                )
            )
        return tuple(hits)

    def _metadata(
        self,
        chunk: GuidelineChunk,
        source: SourceRegistryEntry,
    ) -> ExternalEvidenceMetadata:
        return ExternalEvidenceMetadata(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            title=chunk.title,
            section_title=chunk.section_title,
            section_path=tuple(chunk.section_path),
            canonical_url=chunk.canonical_url,
            published_at=chunk.published_at,
            updated_at=chunk.updated_at,
            retrieved_at=chunk.retrieved_at,
            language=chunk.language,
            topics=tuple(chunk.topics),
            organisation=source.organisation,
            license=chunk.license,
            source_content_hash=chunk.source_content_hash,
            content_hash=chunk.content_hash,
            ingestion_version=chunk.ingestion_version,
            embedding_model=self.embedder.name,
        )


def _metadata_payload(payload: Mapping[str, object]) -> dict[str, object]:
    field_names = ExternalEvidenceMetadata.model_fields
    return {key: value for key, value in payload.items() if key in field_names}


def _qdrant_filter(filters: ExternalEvidenceFilters) -> models.Filter | None:
    must: list[models.Condition] = []
    if filters.topics:
        must.append(
            models.FieldCondition(
                key="topics",
                match=models.MatchAny(any=[item.value for item in filters.topics]),
            )
        )
    if filters.language is not None:
        must.append(
            models.FieldCondition(
                key="language",
                match=models.MatchValue(value=filters.language.value),
            )
        )
    if filters.organisation:
        must.append(
            models.FieldCondition(
                key="organisation_key",
                match=models.MatchValue(value=" ".join(filters.organisation.casefold().split())),
            )
        )
    if filters.updated_from is not None or filters.updated_to is not None:
        must.append(
            models.FieldCondition(
                key="updated_ordinal",
                range=models.Range(
                    gte=(filters.updated_from.toordinal() if filters.updated_from else None),
                    lte=(filters.updated_to.toordinal() if filters.updated_to else None),
                ),
            )
        )
    return models.Filter(must=must) if must else None


def display_citation(metadata: ExternalEvidenceMetadata) -> str:
    section = metadata.section_title or metadata.title
    date_label = metadata.updated_at or metadata.published_at
    date_text = date_label.isoformat() if date_label is not None else "date unavailable"
    return (
        f"{metadata.title} — {metadata.organisation}; {section}; "
        f"{date_text}; {metadata.canonical_url}"
    )


def load_guideline_chunks(path: Path) -> tuple[GuidelineChunk, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"unable to read guideline chunks: {path}") from exc
    chunks: list[GuidelineChunk] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            chunks.append(GuidelineChunk.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"invalid guideline chunk at line {line_number}") from exc
    return tuple(chunks)


def load_valid_registry(path: Path) -> tuple[SourceRegistryEntry, ...]:
    sources, failures = load_registry_with_failures(path)
    if failures:
        summary = ", ".join(f"{item.source_id}:{item.code.value}" for item in failures)
        raise ValueError(f"source registry contains invalid entries: {summary}")
    return sources


def rebuild_qdrant_local(
    *,
    chunks_path: Path,
    registry_path: Path,
    qdrant_path: Path,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedder: EmbeddingModel | None = None,
) -> IndexBuildReport:
    qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(qdrant_path))
    index = QdrantExternalEvidenceIndex(
        client,
        embedder or FastEmbedMultilingualModel(),
        collection_name=collection_name,
    )
    return index.rebuild(load_guideline_chunks(chunks_path), load_valid_registry(registry_path))


def external_recall_at_k(
    cases: Sequence[ExternalRecallCase],
    index: QdrantExternalEvidenceIndex,
    *,
    k: int = 5,
) -> float:
    if not cases:
        raise ValueError("at least one recall case is required")
    if not 1 <= k <= 50:
        raise ValueError("k must be between 1 and 50")
    recalls: list[float] = []
    for case in cases:
        hits = index.search(case.query, top_k=k, filters=case.filters)
        retrieved = {hit.chunk_id for hit in hits}
        recalls.append(len(retrieved & case.relevant_chunk_ids) / len(case.relevant_chunk_ids))
    return sum(recalls) / len(recalls)
