from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from backend.storage.models import UserProfileTable

from .auth import carepath_account_user_id, get_optional_auth_identity
from .errors import CarePathError


def is_synthetic_profile(row: UserProfileTable | None) -> bool:
    if row is None:
        return False
    flags = row.consent_flags
    return isinstance(flags, dict) and flags.get("synthetic_demo") is True


def ensure_user_access(request: Request, session: Session, user_id: UUID) -> None:
    """Keep anonymous demo access while isolating signed-in real-user records."""

    identity = get_optional_auth_identity(request)
    if identity is None:
        return
    if carepath_account_user_id(identity.subject) == user_id:
        return
    if is_synthetic_profile(session.get(UserProfileTable, str(user_id))):
        return
    raise CarePathError(
        "user_scope_forbidden",
        "This signed-in account cannot access the requested user data",
        status_code=HTTPStatus.FORBIDDEN,
    )
