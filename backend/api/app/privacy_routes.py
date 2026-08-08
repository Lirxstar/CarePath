from __future__ import annotations

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict

from backend.storage.private_sessions import PrivateSessionStore

from .errors import CarePathError
from .session_scope import PRIVATE_SESSION_HEADER, parse_private_session_id

router = APIRouter(prefix="/privacy", tags=["privacy"])


class PrivateSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    ttl_minutes: int
    persistent_storage: bool = False


class PrivateSessionEndResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleared: bool


@router.post(
    "/session",
    response_model=PrivateSessionResponse,
    status_code=HTTPStatus.CREATED,
    summary="Create an isolated in-memory data session",
)
def create_private_session(request: Request) -> PrivateSessionResponse:
    store: PrivateSessionStore = request.app.state.private_sessions
    session_id = store.create()
    return PrivateSessionResponse(session_id=session_id, ttl_minutes=store.ttl_minutes)


@router.post(
    "/session/end",
    response_model=PrivateSessionEndResponse,
    summary="Destroy an in-memory private data session",
)
def end_private_session(
    request: Request,
    private_session: Annotated[str | None, Header(alias=PRIVATE_SESSION_HEADER)] = None,
) -> PrivateSessionEndResponse:
    if private_session is None:
        raise CarePathError(
            "private_session_required",
            "A private session identifier is required",
            status_code=HTTPStatus.BAD_REQUEST,
        )
    session_id = parse_private_session_id(private_session)
    store: PrivateSessionStore = request.app.state.private_sessions
    return PrivateSessionEndResponse(cleared=store.close(session_id))
