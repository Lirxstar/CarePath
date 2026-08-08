from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.personalization.plan_calendar import user_local_date
from backend.storage.models import UserProfileTable


def _profile(session: Session, timezone: str) -> str:
    user_id = str(uuid4())
    session.add(
        UserProfileTable(
            user_id=user_id,
            age_band="30-44",
            preferred_language="en",
            timezone=timezone,
            schedule_constraints=None,
            health_goals=["sleep"],
            activity_constraints=None,
            coaching_preferences=None,
            consent_flags={"synthetic_data": True},
        )
    )
    session.flush()
    return user_id


def test_plan_calendar_uses_profile_timezone(database_session: Session) -> None:
    tokyo_user = _profile(database_session, "Asia/Tokyo")
    utc_user = _profile(database_session, "UTC")
    instant = datetime(2026, 8, 8, 16, 30, tzinfo=UTC)

    assert user_local_date(database_session, tokyo_user, instant=instant).isoformat() == "2026-08-09"
    assert user_local_date(database_session, utc_user, instant=instant).isoformat() == "2026-08-08"


def test_invalid_profile_timezone_falls_back_to_utc(database_session: Session) -> None:
    user_id = _profile(database_session, "Invalid/Timezone")
    instant = datetime(2026, 8, 8, 23, 30, tzinfo=UTC)

    assert user_local_date(database_session, user_id, instant=instant).isoformat() == "2026-08-08"
