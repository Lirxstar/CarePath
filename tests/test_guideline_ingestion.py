from hashlib import sha256

import pytest

from backend.domain import KnowledgeChunk
from retrieval.guideline_ingestion import can_ingest, chunk_text


def test_chunk_text_returns_canonical_chunks() -> None:
    source: dict[str, object] = {
        "source_id": "CDC_SLEEP",
        "section_title": "Sleep basics",
    }
    text = "Adults benefit from regular sleep routines."
    chunks = chunk_text(
        text,
        source,
        size=18,
        overlap=4,
        embedding_model="test-embedding",
    )

    assert chunks
    for chunk in chunks:
        assert isinstance(chunk, KnowledgeChunk)
        assert chunk.source_id == "CDC_SLEEP"
        assert chunk.section_title == "Sleep basics"
        assert chunk.embedding_model == "test-embedding"
        expected_hash = sha256(chunk.content.encode()).hexdigest()
        assert chunk.content_hash == expected_hash


def test_content_hash_is_source_independent() -> None:
    text = "same content"
    first_source = {"id": "SOURCE_A"}
    second_source = {"id": "SOURCE_B"}
    first = chunk_text(text, first_source, size=100, overlap=0)[0]
    second = chunk_text(text, second_source, size=100, overlap=0)[0]

    assert first.content_hash == second.content_hash
    assert first.chunk_id != second.chunk_id


def test_overlap_terminates_without_duplicate_final_chunk() -> None:
    source = {"id": "SOURCE"}
    chunks = chunk_text("abcdefghij", source, size=4, overlap=3)
    contents = [chunk.content for chunk in chunks]

    assert contents == [
        "abcd",
        "bcde",
        "cdef",
        "defg",
        "efgh",
        "fghi",
        "ghij",
    ]


def test_invalid_chunk_parameters_are_rejected() -> None:
    source = {"id": "SOURCE"}
    invalid_parameters = [
        (0, 0),
        (-1, 0),
        (4, -1),
        (4, 4),
        (4, 5),
    ]
    for size, overlap in invalid_parameters:
        with pytest.raises(ValueError):
            chunk_text("content", source, size=size, overlap=overlap)


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("   \n\t", {"id": "SOURCE"}) == []


def test_source_id_is_required_for_nonempty_content() -> None:
    with pytest.raises(ValueError):
        chunk_text("content", {})


def test_metadata_only_sources_are_not_ingestable() -> None:
    blocked_statuses = [
        "metadata_only_pending_ai_permission",
        "metadata_only_pending_permission",
    ]
    for status in blocked_statuses:
        assert not can_ingest({"ingestion_status": status})


def test_approved_source_is_ingestable() -> None:
    assert can_ingest({"ingestion_status": "approved"})
