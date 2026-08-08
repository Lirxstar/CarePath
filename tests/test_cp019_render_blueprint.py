from pathlib import Path

BLUEPRINT = Path("render.yaml")


def test_render_blueprint_pins_free_instances() -> None:
    content = BLUEPRINT.read_text(encoding="utf-8")

    assert "  - name: carepath-db\n    plan: free\n" in content
    assert (
        "  - type: web\n    name: carepath-api\n    runtime: docker\n    plan: free\n"
    ) in content
    assert content.count("plan: free") == 2


def test_render_blueprint_keeps_health_and_database_wiring() -> None:
    content = BLUEPRINT.read_text(encoding="utf-8")

    assert "healthCheckPath: /health/ready" in content
    assert "key: CAREPATH_DATABASE_URL" in content
    assert "name: carepath-db\n          property: connectionString" in content
