from __future__ import annotations

import os
from http import HTTPStatus
from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.storage.database import engine as storage_engine
from backend.tokyo.search import TokyoResourceRepository

from .llm.provider import LLMProvider

router = APIRouter(tags=["health"])


def database_health_check() -> None:
    """Verify that the configured SQL database accepts a trivial query."""

    with storage_engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def deployed_git_commit() -> str | None:
    """Return the immutable git identity supplied by the operator or deployment platform."""

    for variable in ("CAREPATH_BUILD_COMMIT", "RENDER_GIT_COMMIT"):
        value = os.getenv(variable)
        if value is not None and value.strip():
            return value.strip()
    return None


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process-level liveness probe with no external dependency checks."""

    return {"status": "ok"}


@router.get("/health/build")
async def build_identity(response: Response) -> dict[str, str | None]:
    """Expose only the public git identity needed to verify an exact deployment."""

    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok", "git_commit": deployed_git_commit()}


@router.get("/health/ready", response_model=None)
async def readiness(request: Request) -> JSONResponse:
    """Dependency-aware readiness probe for the complete CarePath Core service."""

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


@router.get("/health/tokyo", response_model=None)
async def tokyo_readiness(request: Request) -> JSONResponse:
    """Report whether the public Tokyo navigator can serve grounded resource searches.

    Tokyo factual selection depends on the local resource corpus, not on model availability.
    A provider outage is therefore exposed as ``fallback`` while the endpoint remains ready
    when deterministic source-backed search can still operate. Missing resource data is
    blocking and returns 503.
    """

    repository = cast(
        TokyoResourceRepository | None,
        getattr(request.app.state, "tokyo_resource_repository", None),
    )
    resource_count = len(repository) if repository is not None else 0
    resource_ready = resource_count > 0

    active_provider = cast(LLMProvider, request.app.state.provider)
    try:
        provider_health = await active_provider.health_check()
        provider_ready = provider_health.get("status") == "ok"
    except Exception:
        provider_ready = False

    checks = {
        "resource_data": "ok" if resource_ready else "error",
        "provider": "ok" if provider_ready else "fallback",
    }
    return JSONResponse(
        status_code=HTTPStatus.OK if resource_ready else HTTPStatus.SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if resource_ready else "not_ready",
            "checks": checks,
            "resource_count": resource_count,
            "deterministic_search_available": resource_ready,
            "model_assistance_available": provider_ready,
        },
    )
