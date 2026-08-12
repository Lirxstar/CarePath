"""HTTP contracts for deterministic Tokyo search and bounded CP-204/CP-205 assistance."""

from __future__ import annotations

import unicodedata
from http import HTTPStatus
from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.tokyo.agent import TokyoAgentRequest, TokyoAgentResponse, TokyoGroundedResourceAgent
from backend.tokyo.journeys import InterfaceLanguage
from backend.tokyo.models import TokyoResource
from backend.tokyo.safety import (
    TokyoSafetyBoundaryResponse,
    TokyoSafetyDecision,
    assess_tokyo_safety,
)
from backend.tokyo.search import (
    TokyoResourceRepository,
    TokyoResourceSearchRequest,
    TokyoResourceSearchResponse,
)

from .errors import CarePathError
from .llm.provider import LLMProvider

router = APIRouter(prefix="/tokyo", tags=["tokyo"])


class TokyoSafetyTriageRequest(BaseModel):
    """Minimal safety-only contract; precise location is deliberately not accepted."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1500)
    interface_language: InterfaceLanguage

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


def get_tokyo_repository(request: Request) -> TokyoResourceRepository:
    repository = getattr(request.app.state, "tokyo_resource_repository", None)
    if repository is None:
        raise CarePathError(
            "tokyo_resources_unavailable",
            "Tokyo resource corpus is not available",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return cast(TokyoResourceRepository, repository)


def get_model_provider(request: Request) -> LLMProvider:
    provider = getattr(request.app.state, "provider", None)
    if provider is None:
        raise CarePathError(
            "model_provider_unavailable",
            "Model provider is not available",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return cast(LLMProvider, provider)


@router.post("/resources/search", response_model=TokyoResourceSearchResponse)
async def search_tokyo_resources(
    payload: TokyoResourceSearchRequest,
    request: Request,
) -> TokyoResourceSearchResponse:
    """Apply validated hard filters and deterministic location-aware ranking."""

    return get_tokyo_repository(request).search(payload)


@router.post("/safety/triage", response_model=TokyoSafetyDecision)
async def triage_tokyo_request(payload: TokyoSafetyTriageRequest) -> TokyoSafetyDecision:
    """Run CP-205 without accepting, storing, or requiring precise location."""

    return assess_tokyo_safety(payload.query, payload.interface_language)


@router.post(
    "/agent/search",
    response_model=TokyoAgentResponse | TokyoSafetyBoundaryResponse,
)
async def assist_tokyo_resource_search(
    payload: TokyoAgentRequest,
    request: Request,
) -> TokyoAgentResponse | TokyoSafetyBoundaryResponse:
    """Apply CP-205 before CP-204 model use or CP-203 ranking."""

    safety = assess_tokyo_safety(payload.query, payload.interface_language)
    if safety.bypass_resource_navigation:
        return TokyoSafetyBoundaryResponse(safety=safety)

    agent = TokyoGroundedResourceAgent(
        repository=get_tokyo_repository(request),
        provider=get_model_provider(request),
    )
    return await agent.assist(payload)


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
