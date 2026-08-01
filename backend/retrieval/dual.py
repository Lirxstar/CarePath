"""Deterministic personal and external retrieval with stable evidence identifiers."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from backend.domain import KnowledgeChunk

_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]|[\u3040-\u30ff]+")
_MAX_TOP_K = 50


class RetrievalNamespace(StrEnum):
    PERSONAL = "personal"
    EXTERNAL = "external"


@dataclass(frozen=True)
class RetrievalDocument:
    evidence_id: str
    namespace: RetrievalNamespace
    content: str
    source_id: str | None = None
    user_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        if not self.content.strip():
            raise ValueError("content must not be empty")
        if self.namespace is RetrievalNamespace.PERSONAL and not self.user_id:
            raise ValueError("personal documents require user_id")
        if self.namespace is RetrievalNamespace.EXTERNAL and not self.source_id:
            raise ValueError("external documents require source_id")


@dataclass(frozen=True)
class RetrievalHit:
    evidence_id: str
    namespace: RetrievalNamespace
    content: str
    score: float
    source_id: str | None = None
    user_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DualRetrievalResult:
    personal: tuple[RetrievalHit, ...]
    external: tuple[RetrievalHit, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(hit.evidence_id for hit in (*self.personal, *self.external))


@dataclass(frozen=True)
class RecallCase:
    query: str
    namespace: RetrievalNamespace
    relevant_evidence_ids: frozenset[str]
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("recall query must not be empty")
        if not self.relevant_evidence_ids:
            raise ValueError("recall case requires at least one relevant evidence ID")
        if self.namespace is RetrievalNamespace.PERSONAL and not self.user_id:
            raise ValueError("personal recall cases require user_id")


class InMemoryRetrievalStore:
    """Namespace-bound deterministic store used by the prototype and tests."""

    def __init__(self, namespace: RetrievalNamespace) -> None:
        self.namespace = namespace
        self._documents: dict[str, RetrievalDocument] = {}

    def add(self, document: RetrievalDocument) -> None:
        if document.namespace is not self.namespace:
            raise ValueError(
                f"document namespace {document.namespace.value} does not match store "
                f"namespace {self.namespace.value}"
            )
        if document.evidence_id in self._documents:
            raise ValueError(f"duplicate evidence_id: {document.evidence_id}")
        self._documents[document.evidence_id] = document

    def add_many(self, documents: Iterable[RetrievalDocument]) -> None:
        for document in documents:
            self.add(document)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> tuple[RetrievalHit, ...]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= _MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {_MAX_TOP_K}")
        if self.namespace is RetrievalNamespace.PERSONAL and not user_id:
            raise ValueError("personal retrieval requires user_id")

        candidates = [
            document
            for document in self._documents.values()
            if self.namespace is RetrievalNamespace.EXTERNAL or document.user_id == user_id
        ]
        if not candidates:
            return ()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return ()
        document_tokens = {
            document.evidence_id: _tokenize(document.content) for document in candidates
        }
        document_frequency = Counter(
            token
            for tokens in document_tokens.values()
            for token in set(tokens)
            if token in query_tokens
        )
        normalized_query = _normalize_text(query)
        scored: list[tuple[float, RetrievalDocument]] = []
        total_documents = len(candidates)

        for document in candidates:
            tokens = document_tokens[document.evidence_id]
            frequencies = Counter(tokens)
            score = 0.0
            for token, query_count in Counter(query_tokens).items():
                term_frequency = frequencies[token]
                if term_frequency == 0:
                    continue
                inverse_document_frequency = (
                    math.log((total_documents + 1) / (document_frequency[token] + 1)) + 1.0
                )
                score += query_count * (1.0 + math.log(term_frequency)) * inverse_document_frequency
            if normalized_query in _normalize_text(document.content):
                score += 2.0
            if score > 0:
                scored.append((score, document))

        scored.sort(key=lambda item: (-item[0], item[1].evidence_id))
        return tuple(
            RetrievalHit(
                evidence_id=document.evidence_id,
                namespace=document.namespace,
                content=document.content,
                score=score,
                source_id=document.source_id,
                user_id=document.user_id,
                metadata=document.metadata,
            )
            for score, document in scored[:top_k]
        )

    def __len__(self) -> int:
        return len(self._documents)


class DualRetriever:
    """Retrieve separately from personal records and curated external evidence."""

    def __init__(
        self,
        personal_store: InMemoryRetrievalStore,
        external_store: InMemoryRetrievalStore,
    ) -> None:
        if personal_store.namespace is not RetrievalNamespace.PERSONAL:
            raise ValueError("personal_store must use the personal namespace")
        if external_store.namespace is not RetrievalNamespace.EXTERNAL:
            raise ValueError("external_store must use the external namespace")
        self.personal_store = personal_store
        self.external_store = external_store

    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        personal_k: int = 5,
        external_k: int = 5,
    ) -> DualRetrievalResult:
        return DualRetrievalResult(
            personal=self.personal_store.search(query, top_k=personal_k, user_id=user_id),
            external=self.external_store.search(query, top_k=external_k),
        )


def personal_document(
    *,
    record_type: str,
    record_id: str,
    user_id: str,
    content: str,
    metadata: Mapping[str, str] | None = None,
) -> RetrievalDocument:
    record_type = _identity_part(record_type, "record_type")
    record_id = _identity_part(record_id, "record_id")
    user_id = _identity_part(user_id, "user_id")
    return RetrievalDocument(
        evidence_id=f"personal:{record_type}:{record_id}",
        namespace=RetrievalNamespace.PERSONAL,
        content=content,
        user_id=user_id,
        metadata=_metadata_tuple(metadata),
    )


def external_document(
    chunk: KnowledgeChunk,
    *,
    metadata: Mapping[str, str] | None = None,
) -> RetrievalDocument:
    return RetrievalDocument(
        evidence_id=f"external:{chunk.chunk_id}",
        namespace=RetrievalNamespace.EXTERNAL,
        content=chunk.content,
        source_id=chunk.source_id,
        metadata=_metadata_tuple(metadata),
    )


def recall_at_k(
    cases: Sequence[RecallCase],
    *,
    personal_store: InMemoryRetrievalStore,
    external_store: InMemoryRetrievalStore,
    k: int = 5,
) -> float:
    """Return macro Recall@k across deterministic evaluation cases."""
    if not cases:
        raise ValueError("at least one recall case is required")
    if not 1 <= k <= _MAX_TOP_K:
        raise ValueError(f"k must be between 1 and {_MAX_TOP_K}")

    recalls: list[float] = []
    for case in cases:
        if case.namespace is RetrievalNamespace.PERSONAL:
            hits = personal_store.search(case.query, top_k=k, user_id=case.user_id)
        else:
            hits = external_store.search(case.query, top_k=k)
        retrieved = {hit.evidence_id for hit in hits}
        recalls.append(
            len(retrieved & case.relevant_evidence_ids) / len(case.relevant_evidence_ids)
        )
    return sum(recalls) / len(recalls)


def _identity_part(value: str, field_name: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if re.fullmatch(r"[a-z0-9._:-]+", normalized) is None:
        raise ValueError(f"{field_name} contains unsupported characters")
    return normalized


def _metadata_tuple(metadata: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in metadata.items()))


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN_RE.findall(value))
