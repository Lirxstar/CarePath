from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.retrieval import DeterministicHashEmbeddingModel, QdrantExternalEvidenceIndex
from backend.retrieval.guidelines.models import (
    GuidelineChunk,
    GuidelineTopic,
    RedistributionPolicy,
    SourceRegistryEntry,
    sha256_text,
    stable_source_id,
)
from backend.storage.database import Base, create_database_engine, get_session

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


@pytest.fixture
def evidence_api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'evidence-api.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    application = create_app(TEST_SETTINGS)
    application.dependency_overrides[get_session] = override_session
    application.state.external_evidence_index = _external_index()
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _external_index() -> QdrantExternalEvidenceIndex:
    url = "https://example.org/guidelines/sleep"
    source_id = stable_source_id(url)
    content = "A regular sleep schedule and consistent wake time support healthy sleep habits."
    content_hash = sha256_text(content)
    source = SourceRegistryEntry(
        source_id=source_id,
        title="Sleep guidance",
        organisation="Example Public Health",
        canonical_url=url,
        published_at=date(2025, 1, 1),
        updated_at=date(2026, 5, 1),
        retrieved_at=date(2026, 7, 1),
        topics=[GuidelineTopic.SLEEP],
        language="en",
        document_type="guideline",
        authority_type="public_health",
        license="test-permitted",
        redistribution_policy=RedistributionPolicy.FULL_TEXT_ALLOWED,
        full_text_storage_allowed=True,
        notes="API fixture",
    )
    chunk = GuidelineChunk(
        chunk_id="chunk-api-sleep",
        source_id=source_id,
        section_title="Sleep routine",
        content=content,
        embedding_model="cp006-not-embedded",
        content_hash=content_hash,
        title="Sleep guidance",
        section_path=["Sleep routine"],
        canonical_url=url,
        published_at=date(2025, 1, 1),
        updated_at=date(2026, 5, 1),
        language="en",
        topics=[GuidelineTopic.SLEEP],
        chunk_index=0,
        license="test-permitted",
        retrieved_at=date(2026, 7, 1),
        source_content_hash=content_hash,
    )
    index = QdrantExternalEvidenceIndex(
        QdrantClient(":memory:"),
        DeterministicHashEmbeddingModel(),
        collection_name="api-guidelines",
    )
    index.rebuild([chunk], [source])
    return index


def _profile(user_id: str) -> dict[str, object]:
    return {
        "user_id": user_id,
        "age_band": "30-44",
        "preferred_language": "en",
        "timezone": "UTC",
        "health_goals": ["sleep", "physical_activity"],
        "consent_flags": {"synthetic_data": True},
    }


def test_external_evidence_api_returns_score_metadata_and_display_citation(
    evidence_api_client: TestClient,
) -> None:
    response = evidence_api_client.get(
        "/evidence/external/search",
        params={
            "query": "regular sleep schedule wake time",
            "top_k": 5,
            "topics": "sleep",
            "language": "en",
            "organisation": "Example Public Health",
            "updated_from": "2026-01-01",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload[0]["chunk_id"] == "chunk-api-sleep"
    assert isinstance(payload[0]["score"], float)
    assert payload[0]["metadata"]["organisation"] == "Example Public Health"
    assert payload[0]["metadata"]["canonical_url"] == "https://example.org/guidelines/sleep"
    assert "Example Public Health" in payload[0]["citation"]


def test_patient_evidence_api_uses_time_window_metric_filter_and_subjective_label(
    evidence_api_client: TestClient,
) -> None:
    user_id = str(uuid4())
    assert evidence_api_client.post("/profiles", json=_profile(user_id)).status_code == 201
    observations = []
    for day in range(1, 9):
        observations.append(
            {
                "observation_id": str(uuid4()),
                "user_id": user_id,
                "metric_type": "steps",
                "value_numeric": float(4000 + day * 100),
                "value_boolean": None,
                "unit": "steps",
                "observed_at": f"2026-07-{day:02d}T08:00:00+00:00",
                "source_type": "synthetic_wearable",
                "quality_flag": "valid",
                "confidence": 0.95,
            }
        )
    assert (
        evidence_api_client.post(
            "/observations/batch", json={"observations": observations}
        ).status_code
        == 201
    )
    assert (
        evidence_api_client.post(
            "/journals",
            json={
                "entry_id": str(uuid4()),
                "user_id": user_id,
                "created_at": datetime(2026, 7, 8, 20, tzinfo=UTC).isoformat(),
                "text": "My sleep felt irregular tonight.",
                "language": "en",
                "user_tags": ["sleep"],
            },
        ).status_code
        == 201
    )

    response = evidence_api_client.get(
        "/evidence/patient/search",
        params=[
            ("user_id", user_id),
            ("window_days", "7"),
            ("end_at", "2026-07-08T23:00:00+00:00"),
            ("metric_types", "steps"),
            ("keyword", "sleep"),
        ],
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    kinds = {item["kind"] for item in payload["items"]}
    assert "structured_fact" in kinds
    assert "subjective_description" in kinds
    assert any(item["metadata"].get("metric_type") == "steps" for item in payload["items"])


def test_evidence_routes_are_visible_in_openapi(evidence_api_client: TestClient) -> None:
    schema = evidence_api_client.get("/openapi.json").json()

    assert "/evidence/external/search" in schema["paths"]
    assert "/evidence/patient/search" in schema["paths"]
