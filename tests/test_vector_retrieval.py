from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from qdrant_client import QdrantClient

from backend.retrieval import (
    COLLECTION_SCHEMA,
    DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
    INDEX_VERSION,
    DeterministicHashEmbeddingModel,
    ExternalEvidenceFilters,
    ExternalRecallCase,
    QdrantExternalEvidenceIndex,
    external_recall_at_k,
    rebuild_qdrant_local,
)
from backend.retrieval.guidelines.models import (
    GuidelineChunk,
    GuidelineTopic,
    RedistributionPolicy,
    SourceRegistryEntry,
    sha256_text,
    stable_source_id,
)

ROOT = Path(__file__).resolve().parents[1]

_SPECS = (
    (
        "chunk-sleep-routine",
        GuidelineTopic.SLEEP,
        "Regular sleep schedule",
        "A regular sleep schedule and consistent wake time support healthy sleep habits.",
        "Sleep Authority",
    ),
    (
        "chunk-sleep-bedtime",
        GuidelineTopic.SLEEP,
        "Bedtime routine",
        "A consistent bedtime routine can support stable sleep habits and sleep timing.",
        "Sleep Authority",
    ),
    (
        "chunk-activity-walking",
        GuidelineTopic.PHYSICAL_ACTIVITY,
        "Walking and activity",
        "Physical activity can include walking and accumulated active minutes during the day.",
        "Activity Authority",
    ),
    (
        "chunk-activity-weekly",
        GuidelineTopic.PHYSICAL_ACTIVITY,
        "Weekly movement",
        "Moderate activity and regular movement can be accumulated across the week.",
        "Activity Authority",
    ),
    (
        "chunk-stress-breathing",
        GuidelineTopic.STRESS_MANAGEMENT,
        "Paced breathing",
        "Stress management may include paced breathing, relaxation routines, and regular breaks.",
        "Wellbeing Authority",
    ),
    (
        "chunk-stress-recovery",
        GuidelineTopic.STRESS_MANAGEMENT,
        "Recovery time",
        "A stress management routine can include protected recovery time after demanding periods.",
        "Wellbeing Authority",
    ),
    (
        "chunk-falls-balance",
        GuidelineTopic.FALL_PREVENTION,
        "Balance and strength",
        "Fall prevention includes balance, strength, and reducing environmental hazards.",
        "Falls Authority",
    ),
    (
        "chunk-falls-home",
        GuidelineTopic.FALL_PREVENTION,
        "Safer home",
        "Reducing trip hazards in the home can support safer movement and fall prevention.",
        "Falls Authority",
    ),
    (
        "chunk-behaviour-goals",
        GuidelineTopic.BEHAVIOUR_CHANGE,
        "Goals and monitoring",
        "Behaviour change is supported by specific goals, self monitoring, and gradual progress.",
        "Behaviour Authority",
    ),
    (
        "chunk-behaviour-habit",
        GuidelineTopic.BEHAVIOUR_CHANGE,
        "Achievable actions",
        "A small achievable action can make a new habit easier to repeat during behaviour change.",
        "Behaviour Authority",
    ),
    (
        "chunk-help-persistent",
        GuidelineTopic.WHEN_TO_SEEK_PROFESSIONAL_HELP,
        "Persistent symptoms",
        "Seek professional help when concerning symptoms are severe, persistent, or worsening.",
        "Help Authority",
    ),
    (
        "chunk-help-urgent",
        GuidelineTopic.WHEN_TO_SEEK_PROFESSIONAL_HELP,
        "Urgent warning signs",
        "Urgent warning signs can require immediate professional assessment rather than coaching.",
        "Help Authority",
    ),
)


def _corpus() -> tuple[list[SourceRegistryEntry], list[GuidelineChunk]]:
    sources: list[SourceRegistryEntry] = []
    chunks: list[GuidelineChunk] = []
    for index, (chunk_id, topic, title, content, organisation) in enumerate(_SPECS):
        url = f"https://example.org/guidelines/{chunk_id}"
        source_id = stable_source_id(url)
        updated_at = date(2026, 1, 1) if index < 8 else date(2026, 6, 1)
        sources.append(
            SourceRegistryEntry(
                source_id=source_id,
                title=title,
                organisation=organisation,
                canonical_url=url,
                published_at=date(2025, 1, 1),
                updated_at=updated_at,
                retrieved_at=date(2026, 7, 1),
                topics=[topic],
                language="en",
                document_type="guideline",
                authority_type="public_health",
                license="test-permitted",
                redistribution_policy=RedistributionPolicy.FULL_TEXT_ALLOWED,
                full_text_storage_allowed=True,
                notes="Synthetic retrieval evaluation fixture.",
            )
        )
        content_hash = sha256_text(content)
        chunks.append(
            GuidelineChunk(
                chunk_id=chunk_id,
                source_id=source_id,
                section_title=title,
                content=content,
                embedding_model="cp006-not-embedded",
                content_hash=content_hash,
                title=title,
                section_path=[title],
                canonical_url=url,
                published_at=date(2025, 1, 1),
                updated_at=updated_at,
                language="en",
                topics=[topic],
                chunk_index=0,
                license="test-permitted",
                retrieved_at=date(2026, 7, 1),
                source_content_hash=content_hash,
            )
        )
    return sources, chunks


def _index() -> QdrantExternalEvidenceIndex:
    sources, chunks = _corpus()
    index = QdrantExternalEvidenceIndex(
        QdrantClient(":memory:"),
        DeterministicHashEmbeddingModel(),
        collection_name="test-guidelines",
    )
    report = index.rebuild(chunks, sources)
    assert report.chunk_count == 12
    return index


def test_collection_schema_and_multilingual_model_are_versioned() -> None:
    assert COLLECTION_SCHEMA["index_version"] == INDEX_VERSION
    assert COLLECTION_SCHEMA["distance"] == "cosine"
    assert "multilingual" in DEFAULT_MULTILINGUAL_EMBEDDING_MODEL


def test_qdrant_rebuild_returns_verifiable_citation_and_metadata() -> None:
    index = _index()

    hits = index.search("fall prevention balance strength", top_k=5)

    assert hits
    assert hits[0].chunk_id == "chunk-falls-balance"
    assert hits[0].metadata.source_id
    assert hits[0].metadata.organisation == "Falls Authority"
    assert hits[0].metadata.canonical_url.startswith("https://example.org/")
    assert "Falls Authority" in hits[0].citation
    assert hits[0].metadata.index_version == INDEX_VERSION
    assert index.client.count(index.collection_name).count == 12


def test_qdrant_filters_topic_language_organisation_and_update_date() -> None:
    index = _index()

    hits = index.search(
        "goals monitoring gradual progress",
        top_k=5,
        filters=ExternalEvidenceFilters(
            topics=(GuidelineTopic.BEHAVIOUR_CHANGE,),
            language="en",
            organisation="Behaviour Authority",
            updated_from=date(2026, 5, 1),
            updated_to=date(2026, 7, 1),
        ),
    )

    assert hits
    assert all(GuidelineTopic.BEHAVIOUR_CHANGE in hit.metadata.topics for hit in hits)
    assert all(hit.metadata.language.value == "en" for hit in hits)
    assert all(hit.metadata.organisation == "Behaviour Authority" for hit in hits)
    assert all(hit.metadata.updated_at == date(2026, 6, 1) for hit in hits)


def test_twelve_query_gold_fixture_has_calculable_recall_at_5() -> None:
    payload = json.loads(
        (ROOT / "data/evaluation/cp007_vector_retrieval_cases.json").read_text(encoding="utf-8")
    )
    cases = [ExternalRecallCase.model_validate(item) for item in payload["cases"]]

    assert len(cases) == 12
    assert external_recall_at_k(cases, _index(), k=5) == 1.0


def test_rebuild_from_cp006_files_is_one_command_compatible(tmp_path: Path) -> None:
    sources, chunks = _corpus()
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        "\n".join(chunk.model_dump_json() for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    registry_path = tmp_path / "sources.yaml"
    registry_path.write_text(
        json.dumps({"sources": [source.model_dump(mode="json") for source in sources]}),
        encoding="utf-8",
    )
    qdrant_path = tmp_path / "qdrant"

    report = rebuild_qdrant_local(
        chunks_path=chunks_path,
        registry_path=registry_path,
        qdrant_path=qdrant_path,
        collection_name="file-rebuild",
        embedder=DeterministicHashEmbeddingModel(),
    )

    assert report.chunk_count == 12
    reopened = QdrantExternalEvidenceIndex(
        QdrantClient(path=str(qdrant_path)),
        DeterministicHashEmbeddingModel(),
        collection_name="file-rebuild",
    )
    assert reopened.search("regular sleep schedule", top_k=5)[0].chunk_id == "chunk-sleep-routine"
