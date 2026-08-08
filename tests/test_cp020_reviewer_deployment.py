from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app.config import Settings
from backend.api.app.main import create_app


def build_reviewer_fixture(root: Path) -> Path:
    reviewer = root / "reviewer"
    expo = reviewer / "_expo"
    assets = reviewer / "assets"
    expo.mkdir(parents=True)
    assets.mkdir()
    (reviewer / "index.html").write_text(
        "<!doctype html><html><body><div id='root'>CarePath reviewer</div></body></html>",
        encoding="utf-8",
    )
    (expo / "app.js").write_text("console.log('reviewer');\n", encoding="utf-8")
    (assets / "marker.txt").write_text("asset\n", encoding="utf-8")
    return reviewer


def test_integrated_reviewer_web_is_served_without_shadowing_api(tmp_path: Path) -> None:
    reviewer = build_reviewer_fixture(tmp_path)
    application = create_app(
        Settings(environment="test", llm_provider="mock", reviewer_web_dir=str(reviewer))
    )

    with TestClient(application) as client:
        root = client.get("/")
        javascript = client.get("/_expo/app.js")
        asset = client.get("/assets/marker.txt")
        health = client.get("/health")
        missing = client.get("/missing")

    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert "CarePath reviewer" in root.text
    assert root.headers["X-Request-ID"]

    assert javascript.status_code == 200
    assert "reviewer" in javascript.text
    assert asset.status_code == 200
    assert asset.text == "asset\n"

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "provider": "mock"}

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_reviewer_web_configuration_fails_fast_without_index(tmp_path: Path) -> None:
    reviewer = tmp_path / "empty-reviewer"
    reviewer.mkdir()

    with pytest.raises(ValueError, match=r"reviewer_web_dir must contain an Expo Web index\.html"):
        create_app(
            Settings(environment="test", llm_provider="mock", reviewer_web_dir=str(reviewer))
        )
