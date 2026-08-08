from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from backend.storage.models import UserProfileTable

from .auth import carepath_account_user_id, get_optional_auth_identity
from .errors import CarePathError


def _profile_flag(row: UserProfileTable | None, key: str) -> bool:
    if row is None:
        return False
    flags = row.consent_flags
    return isinstance(flags, dict) and flags.get(key) is True


def is_synthetic_profile(row: UserProfileTable | None) -> bool:
    return _profile_flag(row, "synthetic_demo")


def is_account_managed_profile(row: UserProfileTable | None) -> bool:
    return _profile_flag(row, "account_managed")


def ensure_user_access(request: Request, session: Session, user_id: UUID) -> None:
    """Keep anonymous demo access while isolating signed-in real-user records."""

    profile = session.get(UserProfileTable, str(user_id))
    identity = get_optional_auth_identity(request)
    if identity is None:
        if is_account_managed_profile(profile):
            raise CarePathError(
                "authentication_required",
                "Sign in is required to access this saved CarePath data",
                status_code=HTTPStatus.UNAUTHORIZED,
            )
        return
    if carepath_account_user_id(identity.subject) == user_id:
        return
    if is_synthetic_profile(profile):
        return
    raise CarePathError(
        "user_scope_forbidden",
        "This signed-in account cannot access the requested user data",
        status_code=HTTPStatus.FORBIDDEN,
    )
