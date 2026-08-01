"""Normalize Patient Evidence, tool facts, and external guidance without mixing claim scope."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.domain.models import TrustTier

from .patient import PatientEvidenceItem, PatientEvidenceKind
from .vector import ExternalEvidenceHit


class EvidenceType(StrEnum):
    PATIENT_MEASUREMENT = "patient_measurement"
    PATIENT_TOOL_FACT = "patient_tool_fact"
    USER_REPORT = "user_report"
    USER_CONTEXT = "user_context"
    EXTERNAL_GUIDELINE = "external_guideline"


class ClaimScope(StrEnum):
    USER_FACT = "user_fact"
    USER_REPORTED = "user_reported"
    USER_CONTEXT = "user_context"
    GENERAL_GUIDANCE = "general_guidance"


class ToolEvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_record_ids: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None


class GroupedEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    claim_scope: ClaimScope
    content: str = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    source_ids: tuple[str, ...]
    trust_tier: TrustTier
    relevance_score: float | None = None
    citation: str | None = None

    @model_validator(mode="after")
    def enforce_claim_boundary(self) -> GroupedEvidenceItem:
        if (
            self.evidence_type is EvidenceType.USER_REPORT
            and self.claim_scope is not ClaimScope.USER_REPORTED
        ):
            raise ValueError("user reports may only support user-reported claims")
        if (
            self.evidence_type is EvidenceType.EXTERNAL_GUIDELINE
            and self.claim_scope is not ClaimScope.GENERAL_GUIDANCE
        ):
            raise ValueError("external guidelines may only support general guidance")
        return self


class EvidenceBundle(BaseModel):
    """Planner/Verifier input with explicit trust-separated evidence channels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    patient_evidence: tuple[GroupedEvidenceItem, ...]
    external_evidence: tuple[GroupedEvidenceItem, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in (*self.patient_evidence, *self.external_evidence))

    def by_id(self, evidence_id: str) -> GroupedEvidenceItem | None:
        return next(
            (
                item
                for item in (*self.patient_evidence, *self.external_evidence)
                if item.evidence_id == evidence_id
            ),
            None,
        )


class EvidenceAggregator:
    def __init__(self, *, min_external_score: float = 0.05) -> None:
        self.min_external_score = min_external_score

    def build(
        self,
        *,
        patient_items: tuple[PatientEvidenceItem, ...] = (),
        external_hits: tuple[ExternalEvidenceHit, ...] = (),
        tool_facts: tuple[ToolEvidenceFact, ...] = (),
    ) -> EvidenceBundle:
        patient = [self._patient(item) for item in patient_items]
        patient.extend(self._tool(item) for item in tool_facts)
        external = [
            self._external(hit) for hit in external_hits if hit.score >= self.min_external_score
        ]
        return EvidenceBundle(
            patient_evidence=self._deduplicate(patient),
            external_evidence=self._deduplicate(external),
        )

    @staticmethod
    def _patient(item: PatientEvidenceItem) -> GroupedEvidenceItem:
        if item.kind is PatientEvidenceKind.STRUCTURED_FACT:
            evidence_type = EvidenceType.PATIENT_MEASUREMENT
            claim_scope = ClaimScope.USER_FACT
            trust = TrustTier.OBSERVATION
        elif item.kind is PatientEvidenceKind.SUBJECTIVE_DESCRIPTION:
            evidence_type = EvidenceType.USER_REPORT
            claim_scope = ClaimScope.USER_REPORTED
            trust = TrustTier.USER_CONTEXT
        else:
            evidence_type = EvidenceType.USER_CONTEXT
            claim_scope = ClaimScope.USER_CONTEXT
            trust = TrustTier.USER_CONTEXT
        return GroupedEvidenceItem(
            evidence_id=item.evidence_id,
            evidence_type=evidence_type,
            claim_scope=claim_scope,
            content=item.fact,
            start_date=item.start_date,
            end_date=item.end_date,
            source_ids=item.source_record_ids,
            trust_tier=trust,
            relevance_score=1.0,
        )

    @staticmethod
    def _tool(item: ToolEvidenceFact) -> GroupedEvidenceItem:
        return GroupedEvidenceItem(
            evidence_id=item.evidence_id,
            evidence_type=EvidenceType.PATIENT_TOOL_FACT,
            claim_scope=ClaimScope.USER_FACT,
            content=item.content,
            start_date=item.start_date,
            end_date=item.end_date,
            source_ids=item.source_record_ids,
            trust_tier=TrustTier.OBSERVATION,
            relevance_score=1.0,
        )

    @staticmethod
    def _external(hit: ExternalEvidenceHit) -> GroupedEvidenceItem:
        return GroupedEvidenceItem(
            evidence_id=f"external:{hit.chunk_id}",
            evidence_type=EvidenceType.EXTERNAL_GUIDELINE,
            claim_scope=ClaimScope.GENERAL_GUIDANCE,
            content=hit.content,
            start_date=hit.metadata.updated_at or hit.metadata.published_at,
            end_date=hit.metadata.updated_at or hit.metadata.published_at,
            source_ids=(hit.metadata.source_id, hit.chunk_id),
            trust_tier=TrustTier.GUIDELINE,
            relevance_score=hit.score,
            citation=hit.citation,
        )

    @staticmethod
    def _deduplicate(items: list[GroupedEvidenceItem]) -> tuple[GroupedEvidenceItem, ...]:
        by_id: dict[str, GroupedEvidenceItem] = {}
        content_seen: set[str] = set()
        for item in items:
            normalized = " ".join(item.content.casefold().split())
            if item.evidence_id in by_id or normalized in content_seen:
                continue
            by_id[item.evidence_id] = item
            content_seen.add(normalized)
        return tuple(by_id.values())
