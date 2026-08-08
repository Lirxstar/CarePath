from __future__ import annotations

from collections.abc import Generator
from http import HTTPStatus
from typing import cast
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from backend.storage.database import SessionLocal
from backend.storage.private_sessions import PrivateSessionStore

from .errors import CarePathError

PRIVATE_SESSION_HEADER = "X-CarePath-Private-Session"


def parse_private_session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise CarePathError(
            "invalid_private_session",
            "The private session identifier is invalid",
            status_code=HTTPStatus.BAD_REQUEST,
        ) from exc


def get_request_session(request: Request) -> Generator[Session, None, None]:
    raw_session_id = request.headers.get(PRIVATE_SESSION_HEADER)
    if raw_session_id is None:
        with SessionLocal() as session:
            yield session
        return

    session_id = parse_private_session_id(raw_session_id)
    store = cast(PrivateSessionStore, request.app.state.private_sessions)
    try:
        scoped_session = store.open(session_id)
    except KeyError as exc:
        raise CarePathError(
            "private_session_not_found",
            "The private session has ended or expired",
            status_code=HTTPStatus.NOT_FOUND,
        ) from exc

    with scoped_session:
        yield scoped_session
