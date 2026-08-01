import json
from pathlib import Path

import pytest

from backend.domain import KnowledgeChunk
from backend.retrieval import (
    DualRetriever,
    InMemoryRetrievalStore,
    RecallCase,
    RetrievalDocument,
    RetrievalNamespace,
    external_document,
    personal_document,
    recall_at_k,
)

_FIXTURE_PATH = Path("data/evaluation/cp007_retrieval_cases.json")


def _load_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_stores():
    fixture = _load_fixture()
    personal_store = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
    external_store = InMemoryRetrievalStore(RetrievalNamespace.EXTERNAL)
    personal_store.add_many(
        RetrievalDocument(
            evidence_id=item["evidence_id"],
            namespace=RetrievalNamespace.PERSONAL,
            content=item["content"],
            user_id=item["user_id"],
        )
        for item in fixture["personal_documents"]
    )
    external_store.add_many(
        RetrievalDocument(
            evidence_id=item["evidence_id"],
            namespace=RetrievalNamespace.EXTERNAL,
            content=item["content"],
            source_id=item["source_id"],
        )
        for item in fixture["external_documents"]
    )
    return personal_store, external_store


def test_personal_and_external_stores_are_namespace_bound():
    personal_store = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
    external = RetrievalDocument(
        evidence_id="external:chunk-1",
        namespace=RetrievalNamespace.EXTERNAL,
        content="external evidence",
        source_id="src-1",
    )

    with pytest.raises(ValueError, match="does not match store namespace"):
        personal_store.add(external)


def test_personal_search_is_scoped_to_user():
    personal_store, _ = _build_stores()

    hits = personal_store.search("irregular sleep schedule", user_id="user-a")

    assert hits
    assert hits[0].evidence_id == "personal:journal:j-sleep-001"
    assert all(hit.user_id == "user-a" for hit in hits)
    assert "personal:journal:j-sleep-other-user" not in {hit.evidence_id for hit in hits}


def test_external_search_retains_stable_evidence_and_source_ids():
    _, external_store = _build_stores()

    hits = external_store.search("fall prevention balance strength")

    assert hits[0].evidence_id == "external:chunk-falls"
    assert hits[0].source_id == "src-falls"
    assert hits[0].namespace is RetrievalNamespace.EXTERNAL


def test_dual_retriever_returns_separate_result_channels():
    personal_store, external_store = _build_stores()
    retriever = DualRetriever(personal_store, external_store)

    result = retriever.retrieve("walking steps activity", user_id="user-a")

    assert result.personal
    assert result.external
    assert all(hit.namespace is RetrievalNamespace.PERSONAL for hit in result.personal)
    assert all(hit.namespace is RetrievalNamespace.EXTERNAL for hit in result.external)
    assert result.evidence_ids == tuple(
        hit.evidence_id for hit in (*result.personal, *result.external)
    )


def test_personal_document_builds_stable_record_identity():
    document = personal_document(
        record_type="journal",
        record_id="Entry-001",
        user_id="User-A",
        content="Sleep was later than usual.",
        metadata={"date": "2026-07-20"},
    )

    assert document.evidence_id == "personal:journal:entry-001"
    assert document.user_id == "user-a"
    assert document.metadata == (("date", "2026-07-20"),)


def test_external_document_reuses_canonical_chunk_id():
    chunk = KnowledgeChunk(
        chunk_id="chunk-abc123",
        source_id="src-abc123",
        section_title="Sleep",
        content="Keep a regular sleep schedule.",
        embedding_model="deterministic-test",
        content_hash="a" * 64,
    )

    document = external_document(chunk, metadata={"topic": "sleep"})

    assert document.evidence_id == "external:chunk-abc123"
    assert document.source_id == "src-abc123"
    assert document.metadata == (("topic", "sleep"),)


def test_duplicate_evidence_id_is_rejected():
    personal_store = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
    document = personal_document(
        record_type="goal",
        record_id="goal-1",
        user_id="user-a",
        content="Walk after lunch.",
    )
    personal_store.add(document)

    with pytest.raises(ValueError, match="duplicate evidence_id"):
        personal_store.add(document)


def test_invalid_retrieval_requests_are_rejected():
    personal_store, external_store = _build_stores()

    with pytest.raises(ValueError, match="personal retrieval requires user_id"):
        personal_store.search("sleep")
    with pytest.raises(ValueError, match="query must not be empty"):
        external_store.search("   ")
    with pytest.raises(ValueError, match="top_k"):
        external_store.search("sleep", top_k=0)


def test_initial_recall_at_5_evaluation_fixture():
    fixture = _load_fixture()
    personal_store, external_store = _build_stores()
    cases = [
        RecallCase(
            query=item["query"],
            namespace=RetrievalNamespace(item["namespace"]),
            user_id=item.get("user_id"),
            relevant_evidence_ids=frozenset(item["relevant_evidence_ids"]),
        )
        for item in fixture["cases"]
    ]

    score = recall_at_k(
        cases,
        personal_store=personal_store,
        external_store=external_store,
        k=5,
    )

    assert score == pytest.approx(1.0)
