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
    inspector = inspect(engine)
    assert DOMAIN_TABLES.issubset(inspector.get_table_names())
    feedback_columns = {column["name"] for column in inspector.get_columns("plan_feedback")}
    assert "submission_key" in feedback_columns
    feedback_indexes = {index["name"]: index for index in inspector.get_indexes("plan_feedback")}
    assert feedback_indexes["uq_plan_feedback_user_submission_key"]["unique"] == 1

    command.downgrade(config, "base")
    tables = set(inspect(engine).get_table_names())
    assert tables == {"alembic_version"}

    command.upgrade(config, "head")
    assert DOMAIN_TABLES.issubset(inspect(engine).get_table_names())

    engine.dispose()
