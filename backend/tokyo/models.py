"""Canonical models for the bounded CP-201 Tokyo open-data layer."""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TokyoResourceCategory(StrEnum):
    HEALTHCARE = "healthcare"
    COOLING_SHELTER = "cooling_shelter"
    PUBLIC_HEALTH = "public_health"
    FAMILY_SUPPORT = "family_support"
    WOMEN_SUPPORT = "women_support"
    MENTAL_HEALTH_SUPPORT = "mental_health_support"


class SourceFormat(StrEnum):
    CSV = "csv"
    ZIP_CSV = "zip_csv"


class AdapterKind(StrEnum):
    MHLW_MEDICAL = "mhlw_medical"
    TOKYO_ODS = "tokyo_ods"
    TOKYO_WELFARE = "tokyo_welfare"


class Freshness(StrEnum):
    CURRENT = "current"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


class SourceRegistryEntry(BaseModel):
    """One authoritative input dataset used by CarePath Tokyo."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    publisher: str
    catalog_url: str
    download_url: str | None = None
    ckan_dataset_id: str | None = None
    ckan_resource_name: str | None = None
    format: SourceFormat
    adapter: AdapterKind
    category: TokyoResourceCategory
    licence: str
    licence_url: str
    source_as_of: date | None = None
    retrieved_at: date
    max_age_days: int = Field(default=365, ge=1, le=3650)
    region: str = "Tokyo"
    notes: str = ""

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        value = value.strip()
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", value) is None:
            raise ValueError("source_id must be a stable lowercase slug")
        return value

    @field_validator("title", "publisher", "licence", "region")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("catalog_url", "download_url", "licence_url")
    @classmethod
    def absolute_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("URL must be absolute HTTP(S)")
        return value

    @model_validator(mode="after")
    def validate_locator(self) -> SourceRegistryEntry:
        direct = self.download_url is not None
        ckan = self.ckan_dataset_id is not None or self.ckan_resource_name is not None
        if direct == ckan:
            raise ValueError("define exactly one of direct download_url or CKAN locator")
        if ckan and (not self.ckan_dataset_id or not self.ckan_resource_name):
            raise ValueError("CKAN sources require dataset ID and resource name")
        return self


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    sources: list[SourceRegistryEntry]

    @field_validator("sources")
    @classmethod
    def unique_source_ids(cls, value: list[SourceRegistryEntry]) -> list[SourceRegistryEntry]:
        ids = [entry.source_id for entry in value]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be unique")
        if not value:
            raise ValueError("at least one Tokyo source is required")
        if len(value) > 10:
            raise ValueError("hackathon source inventory is bounded to at most 10 datasets")
        return value


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_record_id: str
    source_url: str
    catalog_url: str
    publisher: str
    licence: str
    source_as_of: date | None
    retrieved_at: date
    content_sha256: str

    @field_validator("content_sha256")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        return value


class TokyoResource(BaseModel):
    """Canonical user-visible resource with explicit unknowns and provenance."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    name: str
    category: TokyoResourceCategory
    address: str | None = None
    municipality: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    languages: list[str] = Field(default_factory=list)
    opening_hours: str | None = None
    access_notes: str | None = None
    phone: str | None = None
    website: str | None = None
    freshness: Freshness = Freshness.UNKNOWN
    provenance: list[SourceProvenance] = Field(min_length=1)
    data_quality_flags: list[str] = Field(default_factory=list)

    @field_validator("resource_id", "name")
    @classmethod
    def non_empty_resource_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("resource identifier and name must not be empty")
        return value

    @field_validator("languages", "data_quality_flags")
    @classmethod
    def sorted_unique_strings(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})

    @model_validator(mode="after")
    def validate_location(self) -> TokyoResource:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.address is None and self.latitude is None:
            raise ValueError("resource must have an address or coordinates")
        return self


class SourceBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    input_records: int = 0
    accepted_records: int = 0
    skipped_records: int = 0
    error: str | None = None


class TokyoBuildReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "cp201-v1"
    resources: int
    duplicates_merged: int
    source_results: list[SourceBuildResult]
