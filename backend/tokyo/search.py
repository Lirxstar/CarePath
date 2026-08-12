"""Deterministic geospatial search over the canonical Tokyo resource corpus."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from backend.tokyo.models import Freshness, TokyoResource, TokyoResourceCategory

EARTH_RADIUS_KM = 6371.0088
DEFAULT_SEARCH_RADIUS_KM = 10.0
MAX_SEARCH_RADIUS_KM = 50.0
DEFAULT_SEARCH_RESULTS = 10
MAX_SEARCH_RESULTS = 50


class CoordinateLocation(BaseModel):
    """Precise location supplied for the current search only."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["coordinates"] = "coordinates"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class MunicipalityLocation(BaseModel):
    """Manual fallback using only an explicit municipality label."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["municipality"] = "municipality"
    municipality: str = Field(min_length=1, max_length=80)

    @field_validator("municipality")
    @classmethod
    def normalize_municipality(cls, value: str) -> str:
        normalized = _display_text(value)
        if not normalized:
            raise ValueError("municipality must not be empty")
        return normalized


SearchLocation = Annotated[CoordinateLocation | MunicipalityLocation, Field(discriminator="mode")]


class TokyoResourceFilters(BaseModel):
    """Allow-listed hard constraints over source-backed resource fields."""

    model_config = ConfigDict(extra="forbid")

    category: TokyoResourceCategory | None = None
    required_languages: list[str] = Field(default_factory=list, max_length=8)
    require_known_opening_hours: bool = False
    require_access_notes: bool = False
    require_phone: bool = False
    require_website: bool = False
    allowed_freshness: list[Freshness] = Field(default_factory=list, max_length=4)

    @field_validator("required_languages")
    @classmethod
    def normalize_languages(cls, value: list[str]) -> list[str]:
        normalized = [_normalize_language(item) for item in value]
        normalized = [item for item in normalized if item]
        if len(normalized) != len(set(normalized)):
            raise ValueError("required languages must be unique")
        return sorted(normalized)

    @field_validator("allowed_freshness")
    @classmethod
    def unique_freshness(cls, value: list[Freshness]) -> list[Freshness]:
        if len(value) != len(set(value)):
            raise ValueError("allowed freshness values must be unique")
        return value


class TokyoResourceSearchRequest(BaseModel):
    """Bounded deterministic search request used by API and agent tools."""

    model_config = ConfigDict(extra="forbid")

    location: SearchLocation
    filters: TokyoResourceFilters = Field(default_factory=TokyoResourceFilters)
    radius_km: float = Field(default=DEFAULT_SEARCH_RADIUS_KM, gt=0, le=MAX_SEARCH_RADIUS_KM)
    limit: int = Field(default=DEFAULT_SEARCH_RESULTS, ge=1, le=MAX_SEARCH_RESULTS)


class TokyoResourceSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    distance_km: float | None
    resource: TokyoResource


class NoMatchDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["no_matching_resources"] = "no_matching_resources"
    message: str
    hard_constraints: list[str]


class TokyoResourceSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "no_match"]
    location: SearchLocation
    radius_km: float | None
    applied_filters: TokyoResourceFilters
    count: int = Field(ge=0)
    results: list[TokyoResourceSearchResult]
    no_match: NoMatchDetail | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "ok" and (not self.results or self.no_match is not None):
            raise ValueError("ok search responses require results and no no-match detail")
        if self.status == "no_match" and (self.results or self.no_match is None):
            raise ValueError("no-match responses require an empty result list and detail")
        if self.count != len(self.results):
            raise ValueError("search count must equal result length")
        return self


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return deterministic great-circle distance in kilometres."""

    _validate_coordinate(latitude_a, longitude_a)
    _validate_coordinate(latitude_b, longitude_b)
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    central_angle = 2 * math.atan2(math.sqrt(haversine), math.sqrt(max(0.0, 1 - haversine)))
    return EARTH_RADIUS_KM * central_angle


class TokyoResourceRepository:
    """Immutable in-memory index with deterministic filtering and ranking."""

    def __init__(self, resources: Iterable[TokyoResource]):
        ordered = tuple(sorted(resources, key=lambda item: item.resource_id))
        ids = [resource.resource_id for resource in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("Tokyo resource IDs must be unique")
        self._resources = ordered
        self._by_id = {resource.resource_id: resource for resource in ordered}

    @classmethod
    def from_jsonl(cls, path: Path) -> TokyoResourceRepository:
        """Load a strict CP-201 JSONL artifact without repairing invalid records."""

        resources: list[TokyoResource] = []
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                resources.append(TokyoResource.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"invalid Tokyo resource at line {line_number}") from exc
        return cls(resources)

    def __len__(self) -> int:
        return len(self._resources)

    def get(self, resource_id: str) -> TokyoResource | None:
        return self._by_id.get(resource_id)

    def search(self, request: TokyoResourceSearchRequest) -> TokyoResourceSearchResponse:
        """Apply allow-listed hard constraints, then deterministic distance/ID ranking."""

        matches: list[tuple[TokyoResource, float | None]] = []
        for resource in self._resources:
            if not _matches_filters(resource, request.filters):
                continue

            distance_km: float | None = None
            if isinstance(request.location, CoordinateLocation):
                if resource.latitude is None or resource.longitude is None:
                    continue
                distance_km = haversine_distance_km(
                    request.location.latitude,
                    request.location.longitude,
                    resource.latitude,
                    resource.longitude,
                )
                if distance_km > request.radius_km:
                    continue
            else:
                if resource.municipality is None:
                    continue
                if _identity_text(resource.municipality) != _identity_text(
                    request.location.municipality
                ):
                    continue

            matches.append((resource, distance_km))

        matches.sort(
            key=lambda item: (
                math.inf if item[1] is None else item[1],
                item[0].resource_id,
            )
        )
        selected = matches[: request.limit]
        results = [
            TokyoResourceSearchResult(
                rank=index,
                distance_km=None if distance is None else round(distance, 3),
                resource=resource,
            )
            for index, (resource, distance) in enumerate(selected, 1)
        ]
        radius = request.radius_km if isinstance(request.location, CoordinateLocation) else None
        if results:
            return TokyoResourceSearchResponse(
                status="ok",
                location=request.location,
                radius_km=radius,
                applied_filters=request.filters,
                count=len(results),
                results=results,
            )
        return TokyoResourceSearchResponse(
            status="no_match",
            location=request.location,
            radius_km=radius,
            applied_filters=request.filters,
            count=0,
            results=[],
            no_match=NoMatchDetail(
                message="No Tokyo resource satisfies all requested hard constraints.",
                hard_constraints=_hard_constraint_names(request),
            ),
        )


def _matches_filters(resource: TokyoResource, filters: TokyoResourceFilters) -> bool:
    if filters.category is not None and resource.category is not filters.category:
        return False
    if filters.required_languages:
        known_languages = {_normalize_language(item) for item in resource.languages}
        if not set(filters.required_languages).issubset(known_languages):
            return False
    if filters.require_known_opening_hours and not _present(resource.opening_hours):
        return False
    if filters.require_access_notes and not _present(resource.access_notes):
        return False
    if filters.require_phone and not _present(resource.phone):
        return False
    if filters.require_website and not _present(resource.website):
        return False
    return not filters.allowed_freshness or resource.freshness in filters.allowed_freshness


def _hard_constraint_names(request: TokyoResourceSearchRequest) -> list[str]:
    constraints: list[str] = []
    filters = request.filters
    if filters.category is not None:
        constraints.append("category")
    if filters.required_languages:
        constraints.append("required_languages")
    if filters.require_known_opening_hours:
        constraints.append("known_opening_hours")
    if filters.require_access_notes:
        constraints.append("access_notes")
    if filters.require_phone:
        constraints.append("phone")
    if filters.require_website:
        constraints.append("website")
    if filters.allowed_freshness:
        constraints.append("freshness")
    if isinstance(request.location, CoordinateLocation):
        constraints.append("radius_km")
    else:
        constraints.append("municipality")
    return constraints


def _validate_coordinate(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")


def _normalize_language(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _display_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _identity_text(value: str) -> str:
    return _display_text(value).casefold()


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())
