"""HTTP contracts for deterministic Tokyo public-resource search."""

from __future__ import annotations

from http import HTTPStatus
from typing import cast

from fastapi import APIRouter, Request

from backend.tokyo.models import TokyoResource
from backend.tokyo.search import (
    TokyoResourceRepository,
    TokyoResourceSearchRequest,
    TokyoResourceSearchResponse,
)

from .errors import CarePathError

router = APIRouter(prefix="/tokyo", tags=["tokyo"])


def get_tokyo_repository(request: Request) -> TokyoResourceRepository:
    repository = getattr(request.app.state, "tokyo_resource_repository", None)
    if repository is None:
        raise CarePathError(
            "tokyo_resources_unavailable",
            "Tokyo resource corpus is not available",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return cast(TokyoResourceRepository, repository)


@router.post("/resources/search", response_model=TokyoResourceSearchResponse)
async def search_tokyo_resources(
    payload: TokyoResourceSearchRequest,
    request: Request,
) -> TokyoResourceSearchResponse:
    """Apply validated hard filters and deterministic location-aware ranking."""

    return get_tokyo_repository(request).search(payload)


@router.get("/resources/{resource_id}", response_model=TokyoResource)
async def get_tokyo_resource(resource_id: str, request: Request) -> TokyoResource:
    """Return one canonical source-backed resource without generated fields."""

    resource = get_tokyo_repository(request).get(resource_id)
    if resource is None:
        raise CarePathError(
            "tokyo_resource_not_found",
            "Tokyo resource was not found",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return resource
