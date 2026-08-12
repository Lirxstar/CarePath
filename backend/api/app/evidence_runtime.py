"""Shared runtime ownership for external guideline evidence search."""

from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from fastapi import Request
from qdrant_client import QdrantClient

from backend.retrieval import (
    BundledExternalEvidenceIndex,
    ExternalEvidenceFilters,
    ExternalEvidenceHit,
    FastEmbedMultilingualModel,
    QdrantExternalEvidenceIndex,
)

from .config import Settings
from .errors import CarePathError

logger = logging.getLogger("carepath.api")
_INITIALIZATION_LOCK = Lock()


class ExternalEvidenceSearchIndex(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: ExternalEvidenceFilters | None = None,
    ) -> tuple[ExternalEvidenceHit, ...]: ...


def get_external_evidence_index(request: Request) -> ExternalEvidenceSearchIndex:
    """Return one process-owned index, preferring a built CP-007 Qdrant collection."""

    cached = getattr(request.app.state, "external_evidence_index", None)
    if cached is not None and callable(getattr(cached, "search", None)):
        return cast(ExternalEvidenceSearchIndex, cached)

    with _INITIALIZATION_LOCK:
        cached = getattr(request.app.state, "external_evidence_index", None)
        if cached is not None and callable(getattr(cached, "search", None)):
            return cast(ExternalEvidenceSearchIndex, cached)

        settings = cast(Settings, request.app.state.settings)
        index = _load_qdrant_index(settings)
        backend = "qdrant"
        if index is None:
            index = _load_bundled_index(settings)
            backend = "bundled"
        if index is None:
            raise CarePathError(
                "evidence_index_unavailable",
                "External guideline evidence is temporarily unavailable",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )

        request.app.state.external_evidence_index = index
        request.app.state.external_evidence_backend = backend
        request.app.state.external_evidence_index_owned = True
        logger.info("external_evidence_ready", extra={"evidence_backend": backend})
        return index


def optional_external_evidence_index(request: Request) -> ExternalEvidenceSearchIndex | None:
    """Return evidence when available while preserving the Coach safety-degrade path."""

    try:
        return get_external_evidence_index(request)
    except CarePathError:
        return None


def close_external_evidence_index(application: object) -> None:
    """Close only an index created and owned by this runtime helper."""

    state = getattr(application, "state", None)
    if state is None or not getattr(state, "external_evidence_index_owned", False):
        return
    index = getattr(state, "external_evidence_index", None)
    client = getattr(index, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()
    state.external_evidence_index = None
    state.external_evidence_index_owned = False


def _load_qdrant_index(settings: Settings) -> QdrantExternalEvidenceIndex | None:
    path = Path(settings.evidence_index_path)
    if not _directory_has_content(path):
        return None

    client: QdrantClient | None = None
    try:
        client = QdrantClient(path=str(path))
        if not client.collection_exists(settings.evidence_collection_name):
            client.close()
            return None
        return QdrantExternalEvidenceIndex(
            client,
            FastEmbedMultilingualModel(model_name=settings.evidence_embedding_model),
            collection_name=settings.evidence_collection_name,
        )
    except Exception as exc:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        logger.warning(
            "external_qdrant_unavailable",
            extra={"error_class": type(exc).__name__},
        )
        return None


def _load_bundled_index(settings: Settings) -> BundledExternalEvidenceIndex | None:
    path = Path(settings.evidence_bundle_path)
    if not path.is_file():
        return None
    try:
        return BundledExternalEvidenceIndex.from_path(path)
    except (ValueError, OSError) as exc:
        logger.warning(
            "external_bundle_unavailable",
            extra={"error_class": type(exc).__name__},
        )
        return None


def _directory_has_content(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except (StopIteration, OSError):
        return False
    return True
