from __future__ import annotations

from http import HTTPStatus
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.storage.database import engine as storage_engine

from .llm.provider import LLMProvider

router = APIRouter(tags=["health"])


def database_health_check() -> None:
    """Verify that the configured SQL database accepts a trivial query."""

    with storage_engine.connect() as connection:
        connection.execute(text("SELECT 1"))


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process-level liveness probe with no external dependency checks."""

    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
async def readiness(request: Request) -> JSONResponse:
    """Dependency-aware readiness probe for orchestrators and cloud platforms."""

    checks: dict[str, str] = {}

    try:
        database_health_check()
    except Exception:
        checks["database"] = "error"
    else:
        checks["database"] = "ok"

    active_provider = cast(LLMProvider, request.app.state.provider)
    try:
        provider_health = await active_provider.health_check()
        provider_ready = provider_health.get("status") == "ok"
    except Exception:
        provider_ready = False
    checks["provider"] = "ok" if provider_ready else "error"

    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        },
    )
