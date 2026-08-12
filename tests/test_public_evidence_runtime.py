from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api.app.evidence_runtime as evidence_runtime
from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.retrieval import BundledExternalEvidenceIndex

BUNDLE_PATH = Path("data/guidelines/public_evidence_bundle.json")
REGISTRY_PATH = Path("data/guidelines/sources.yaml")


def _settings(tmp_path: Path, *, bundle_path: Path = BUNDLE_PATH) -> Settings:
    index_path = tmp_path / "qdrant"
    index_path.mkdir()
    return Settings(
        environment="test",
        llm_provider="mock",
        evidence_index_path=str(index_path),
        evidence_bundle_path=str(bundle_path),
    )


def test_public_bundle_returns_source_backed_activity_evidence() -> None:
    index = BundledExternalEvidenceIndex.from_path(BUNDLE_PATH)

    hits = index.search("My activity and daily movement have dropped", top_k=5)

    assert hits
    assert hits[0].metadata.source_id == "src-e979225fc93f357e"
    assert hits[0].metadata.organisation == "Centers for Disease Control and Prevention"
    assert hits[0].metadata.canonical_url.startswith("https://www.cdc.gov/")
    assert hits[0].metadata.embedding_model == "carepath-deterministic-lexical-v1"
    assert "Centers for Disease Control and Prevention" in hits[0].citation


def test_public_bundle_sources_are_redistributable_registry_entries() -> None:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    sources = {item["source_id"]: item for item in registry["sources"]}

    assert bundle["entries"]
    for entry in bundle["entries"]:
        source = sources[entry["source_id"]]
        assert source["redistribution_policy"] == "full_text_allowed"
        assert source["full_text_storage_allowed"] is True
        assert entry["organisation"] == source["organisation"]
        assert entry["license"] == source["license"]


def test_empty_qdrant_directory_uses_bundled_fallback(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))

    with TestClient(application) as client:
        response = client.get(
            "/evidence/external/search",
            params={"query": "walking movement activity", "top_k": 3},
        )

    assert response.status_code == 200, response.text
    assert response.json()
    assert application.state.external_evidence_backend == "bundled"


def test_qdrant_runtime_error_falls_back_without_returning_500(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    Path(settings.evidence_index_path, "marker").write_text("broken", encoding="utf-8")

    class BrokenQdrantClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated local Qdrant initialization failure")

    monkeypatch.setattr(evidence_runtime, "QdrantClient", BrokenQdrantClient)
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.get(
            "/evidence/external/search",
            params={"query": "sleep bedtime routine", "top_k": 3},
        )

    assert response.status_code == 200, response.text
    assert response.json()
    assert application.state.external_evidence_backend == "bundled"


def test_missing_all_evidence_backends_returns_controlled_503(tmp_path: Path) -> None:
    missing_bundle = tmp_path / "missing-bundle.json"
    application = create_app(_settings(tmp_path, bundle_path=missing_bundle))

    with TestClient(application) as client:
        response = client.get(
            "/evidence/external/search",
            params={"query": "activity", "top_k": 3},
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "evidence_index_unavailable"
    assert "Internal server error" not in response.text


def test_render_platform_health_check_is_dependency_free_liveness() -> None:
    blueprint = Path("render.yaml").read_text(encoding="utf-8")

    assert "healthCheckPath: /health/live" in blueprint
    assert "healthCheckPath: /health/ready" not in blueprint


def test_reviewer_image_copies_public_bundle_without_qdrant_artifact() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY data/guidelines/public_evidence_bundle.json" in dockerfile
    assert "COPY data/guidelines/qdrant" not in dockerfile
