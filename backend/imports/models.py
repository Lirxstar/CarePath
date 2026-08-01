from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImportIssue(BaseModel):
    """One explicit validation, repair, skip, or interoperability finding."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    record_index: int | None = Field(default=None, ge=0)
    resource_type: str | None = None
    original_value: str | None = None


class ImportReport(BaseModel):
    """Auditable outcome returned for every import attempt."""

    model_config = ConfigDict(extra="forbid")

    import_id: UUID = Field(default_factory=uuid4)
    status: Literal["success", "partial", "failed"]
    source_format: Literal["csv", "json", "fhir"]
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    imported_at: datetime
    received_records: int = Field(ge=0)
    inserted_records: int = Field(ge=0)
    fixed_issues: list[ImportIssue] = Field(default_factory=list)
    skipped_records: list[ImportIssue] = Field(default_factory=list)
    blocking_errors: list[ImportIssue] = Field(default_factory=list)

    @field_validator("imported_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("imported_at must include a timezone")
        return value.astimezone(UTC)


class PreparedImport(BaseModel):
    """Validated canonical payload waiting for one transactional persistence step."""

    model_config = ConfigDict(extra="forbid")

    report: ImportReport
    user_profiles: list[dict[str, object]] = Field(default_factory=list)
    observations: list[dict[str, object]] = Field(default_factory=list)
    journal_entries: list[dict[str, object]] = Field(default_factory=list)
    goals: list[dict[str, object]] = Field(default_factory=list)
    interactions: list[dict[str, object]] = Field(default_factory=list)
    intervention_plans: list[dict[str, object]] = Field(default_factory=list)
    plan_actions: list[dict[str, object]] = Field(default_factory=list)
    plan_feedback: list[dict[str, object]] = Field(default_factory=list)
