from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.storage.database import get_session
from backend.storage.models import ObservationTable, UserProfileTable

from .auth import carepath_account_user_id, require_auth_identity
from .config import Settings

router = APIRouter(tags=["auth"])
PersistentSessionDependency = Annotated[Session, Depends(get_session)]


class PublicRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_enabled: bool
    supabase_url: str | None
    supabase_publishable_key: str | None
    private_mode_available: bool = True
    private_session_ttl_minutes: int


class AuthMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: bool = True
    carepath_user_id: UUID
    email: str | None
    profile_exists: bool
    latest_observation_at: datetime | None


@router.get(
    "/config/public",
    response_model=PublicRuntimeConfig,
    summary="Return non-secret runtime configuration for the client",
)
def public_runtime_config(request: Request) -> PublicRuntimeConfig:
    settings: Settings = request.app.state.settings
    key = settings.supabase_publishable_key
    auth_enabled = settings.supabase_url is not None and key is not None
    return PublicRuntimeConfig(
        auth_enabled=auth_enabled,
        supabase_url=settings.supabase_url if auth_enabled else None,
        supabase_publishable_key=key.get_secret_value()
        if auth_enabled and key is not None
        else None,
        private_session_ttl_minutes=settings.private_session_ttl_minutes,
    )


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    summary="Resolve a signed-in account to its stable CarePath user id",
)
def auth_me(request: Request, session: PersistentSessionDependency) -> AuthMeResponse:
    identity = require_auth_identity(request)
    user_id = carepath_account_user_id(identity.subject)
    profile_exists = session.get(UserProfileTable, str(user_id)) is not None
    latest_observation_at = session.scalar(
        select(func.max(ObservationTable.observed_at)).where(
            ObservationTable.user_id == str(user_id)
        )
    )
    return AuthMeResponse(
        carepath_user_id=user_id,
        email=identity.email,
        profile_exists=profile_exists,
        latest_observation_at=latest_observation_at,
    )
