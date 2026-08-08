from __future__ import annotations

from datetime import UTC, date, datetime, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.storage.models import UserProfileTable


def user_local_date(
    session: Session,
    user_id: UUID | str,
    *,
    instant: datetime | None = None,
) -> date:
    """Resolve a plan calendar date in the user's configured IANA timezone."""
    profile = session.get(UserProfileTable, str(user_id))
    if profile is None:
        raise ValueError("patient profile does not exist")

    resolved = instant or datetime.now(UTC)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        resolved = resolved.replace(tzinfo=UTC)
    else:
        resolved = resolved.astimezone(UTC)

    zone: tzinfo
    try:
        zone = ZoneInfo(profile.timezone)
    except ZoneInfoNotFoundError:
        zone = UTC
    return resolved.astimezone(zone).date()
