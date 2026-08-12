from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app.config import Settings
from backend.api.app.llm.mock import MockLLMProvider
from backend.api.app.main import create_app
from backend.tokyo.search import TokyoResourceRepository


def _app(tmp_path: Path):
    reviewer = tmp_path / "reviewer"
    reviewer.mkdir()
    (reviewer / "index.html").write_text(
        "<!DOCTYPE html><html><body>CarePath reviewer</body></html>",
        encoding="utf-8",
    )
    return create_app(
        settings=Settings(
            environment="test",
            reviewer_web_dir=str(reviewer),
            llm_provider="mock",
        ),
        provider=MockLLMProvider(),
        tokyo_repository=TokyoResourceRepository([]),
    )


def test_tokyo_entry_serves_same_expo_document_without_replacing_core(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        core = client.get("/")
        tokyo = client.get("/tokyo")
        tokyo_slash = client.get("/tokyo/")

    assert core.status_code == 200
    assert tokyo.status_code == 200
    assert tokyo_slash.status_code == 200
    assert core.headers["content-type"].startswith("text/html")
    assert tokyo.headers["content-type"].startswith("text/html")
    assert tokyo.text == core.text == tokyo_slash.text
    assert "CarePath reviewer" in tokyo.text


def test_tokyo_spa_entry_does_not_shadow_tokyo_api_routes(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        triage = client.post(
            "/tokyo/safety/triage",
            json={
                "query": "I need a nearby clinic where staff can support me in English.",
                "interface_language": "en",
            },
        )
        search = client.post(
            "/tokyo/agent/search",
            json={
                "query": "I need a nearby cooling shelter.",
                "interface_language": "en",
                "location": {"mode": "municipality", "municipality": "江東区"},
                "radius_km": 10,
                "limit": 5,
            },
        )

    assert triage.status_code == 200
    assert triage.json()["disposition"] == "routine_navigation"
    assert search.status_code == 200
    assert search.json()["status"] == "no_match"
    assert search.json()["search"]["status"] == "no_match"
