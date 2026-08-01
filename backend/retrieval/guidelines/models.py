"""Typed CP-006 registry, provenance, and ingestion result models."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.domain import KnowledgeChunk, KnowledgeSource
from backend.domain.models import Language, TrustTier

INGESTION_VERSION = "cp006-v1"
PARSER_VERSION = "1"
CLEANER_VERSION = "1"
CHUNKER_VERSION = "1"


class GuidelineTopic(StrEnum):
    PHYSICAL_ACTIVITY = "physical_activity"
    SLEEP = "sleep"
    STRESS_MANAGEMENT = "stress_management"
    FALL_PREVENTION = "fall_prevention"
    BEHAVIOUR_CHANGE = "behaviour_change"
    WHEN_TO_SEEK_PROFESSIONAL_HELP = "when_to_seek_professional_help"


class SourceFormat(StrEnum):
    HTML = "html"
    MARKDOWN = "markdown"
    TEXT = "text"
    PDF_TEXT = "pdf_text"


class RedistributionPolicy(StrEnum):
    FULL_TEXT_ALLOWED = "full_text_allowed"
    DERIVED_CHUNKS_ALLOWED = "derived_chunks_allowed"
    METADATA_ONLY = "metadata_only"
    UNKNOWN = "unknown"


class FailureCode(StrEnum):
    FETCH_ERROR = "fetch_error"
    UNSUPPORTED_FORMAT = "unsupported_format"
    PARSE_ERROR = "parse_error"
    EMPTY_CONTENT = "empty_content"
    LICENSE_RESTRICTED = "license_restricted"
    INVALID_METADATA = "invalid_metadata"
    DUPLICATE = "duplicate"


class SourceRegistryEntry(BaseModel):
    """Curated registry entry that maps into canonical ``KnowledgeSource``."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    source_id: str
    title: str
    organisation: str
    canonical_url: str
    published_at: date | None = None
    updated_at: date | None = None
    retrieved_at: date
    topics: list[GuidelineTopic]
    language: Language
    document_type: str
    authority_type: str
    license: str
    redistribution_policy: RedistributionPolicy
    full_text_storage_allowed: bool
    notes: str
    aliases: list[str] = Field(default_factory=list)

    @field_validator(
        "source_id",
        "title",
        "organisation",
        "canonical_url",
        "document_type",
        "authority_type",
        "license",
        "notes",
    )
    @classmethod
    def non_empty_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("topics")
    @classmethod
    def unique_topics(cls, value: list[GuidelineTopic]) -> list[GuidelineTopic]:
        if not value:
            raise ValueError("topics must contain at least one topic")
        if len(value) != len(set(value)):
            raise ValueError("topics must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_identity_and_storage_policy(self) -> SourceRegistryEntry:
        normalized = normalize_url(self.canonical_url)
        expected = stable_source_id(normalized)
        if self.source_id != expected:
            raise ValueError("source_id must match the deterministic canonical URL ID")
        if (
            self.redistribution_policy
            in {
                RedistributionPolicy.METADATA_ONLY,
                RedistributionPolicy.UNKNOWN,
                RedistributionPolicy.DERIVED_CHUNKS_ALLOWED,
            }
            and self.full_text_storage_allowed
        ):
            raise ValueError(
                "full_text_storage_allowed can only be true for full_text_allowed sources"
            )
        return self

    def to_domain(self) -> GuidelineSource:
        published_or_updated_at = self.updated_at or self.published_at
        return GuidelineSource(
            source_id=self.source_id,
            title=self.title,
            organisation=self.organisation,
            url=normalize_url(self.canonical_url),
            published_or_updated_at=published_or_updated_at,
            retrieved_at=self.retrieved_at,
            trust_tier=TrustTier.GUIDELINE,
            licence_note=self.license,
            canonical_url=normalize_url(self.canonical_url),
            published_at=self.published_at,
            updated_at=self.updated_at,
            topics=self.topics,
            language=self.language,
            document_type=self.document_type,
            authority_type=self.authority_type,
            license=self.license,
            redistribution_policy=self.redistribution_policy,
            full_text_storage_allowed=self.full_text_storage_allowed,
            notes=self.notes,
            aliases=self.aliases,
        )


class GuidelineSource(KnowledgeSource):
    """Canonical knowledge source plus CP-006 curation metadata."""

    canonical_url: str
    published_at: date | None = None
    updated_at: date | None = None
    topics: list[GuidelineTopic]
    language: Language
    document_type: str
    authority_type: str
    license: str
    redistribution_policy: RedistributionPolicy
    full_text_storage_allowed: bool
    notes: str
    aliases: list[str] = Field(default_factory=list)
    source_content_hash: str | None = None


class GuidelineChunk(KnowledgeChunk):
    """Canonical knowledge chunk plus complete CP-006 provenance."""

    title: str
    section_path: list[str]
    canonical_url: str
    published_at: date | None = None
    updated_at: date | None = None
    language: Language
    topics: list[GuidelineTopic]
    chunk_index: int = Field(ge=0)
    license: str
    retrieved_at: date
    source_content_hash: str
    ingestion_version: str = INGESTION_VERSION
    parser_version: str = PARSER_VERSION
    cleaner_version: str = CLEANER_VERSION
    chunker_version: str = CHUNKER_VERSION

    @field_validator("source_content_hash")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("source_content_hash must be a SHA-256 hex digest")
        return value


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int = 800
    chunk_overlap: int = 120
    minimum_chunk_size: int = 80

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must satisfy 0 <= overlap < chunk_size")
        if self.minimum_chunk_size <= 0 or self.minimum_chunk_size > self.chunk_size:
            raise ValueError("minimum_chunk_size must be in (0, chunk_size]")


@dataclass(frozen=True)
class Section:
    path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class IngestionFailure:
    source_id: str
    code: FailureCode
    reason: str


@dataclass(frozen=True)
class IngestionResult:
    source: GuidelineSource
    source_content_hash: str | None
    chunks: tuple[GuidelineChunk, ...]
    failure: IngestionFailure | None = None
    duplicate_of: str | None = None


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("canonical_url must be an absolute HTTP(S) URL")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = [
        (key, query_value)
        for key, query_value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query_pairs)), ""))


def stable_source_id(canonical_url: str) -> str:
    normalized = normalize_url(canonical_url)
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"src-{digest[:16]}"


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def stable_chunk_id(
    source_id: str,
    section_path: tuple[str, ...],
    chunk_index: int,
    content_hash: str,
) -> str:
    section_identity = "/".join(section_path)
    payload = f"{source_id}|{section_identity}|{chunk_index}|{content_hash}"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"chunk-{digest[:20]}"
