from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_TABLES = {
    "user_profiles",
    "observations",
    "journal_entries",
    "goals",
    "interactions",
    "intervention_plans",
    "plan_actions",
    "plan_feedback",
    "audit_events",
    "data_imports",
}


def test_alembic_upgrade_and_downgrade(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "migration.db"
    monkeypatch.setenv("CAREPATH_DATABASE_URL", f"sqlite:///{database}")

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database}")
    assert DOMAIN_TABLES.issubset(inspect(engine).get_table_names())

    command.downgrade(config, "base")
    tables = set(inspect(engine).get_table_names())
    assert tables == {"alembic_version"}

    command.upgrade(config, "head")
    assert DOMAIN_TABLES.issubset(inspect(engine).get_table_names())

    engine.dispose()
