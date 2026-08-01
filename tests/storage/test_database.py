from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.storage.database import Base
from backend.storage.models import UserProfileTable


def test_create_and_read_database_entity(database_session: Session) -> None:
    user = UserProfileTable(
        user_id="user-1",
        age_band="18-29",
        preferred_language="en",
        timezone="UTC",
        health_goals=[],
        consent_flags={},
    )
    database_session.add(user)
    database_session.flush()

    rows = database_session.scalars(select(UserProfileTable)).all()

    assert len(rows) == 1
    assert rows[0].user_id == "user-1"


def test_schema_contains_required_tables() -> None:
    assert {
        "user_profiles",
        "observations",
        "journal_entries",
        "goals",
        "interactions",
        "intervention_plans",
        "plan_actions",
        "plan_feedback",
        "audit_events",
    }.issubset(Base.metadata.tables)
