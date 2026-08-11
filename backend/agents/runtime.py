"""Production-facing deterministic wiring for one bounded coaching interaction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.personalization.planner_v2 import (
    PersonalizedInterventionPlanner,
    PersonalizedWeeklyPlan,
)
from backend.retrieval import (
    DualRetriever,
    ExternalEvidenceHit,
    InMemoryRetrievalStore,
    PatientEvidenceItem,
    PatientEvidenceQuery,
    PatientEvidenceService,
    RetrievalDocument,
    RetrievalHit,
    RetrievalNamespace,
)
from backend.retrieval.evidence import EvidenceAggregator, EvidenceBundle
from backend.retrieval.sanitizer import sanitize_retrieved_content
from backend.safety import StrictGroundingSafetyVerifier
from backend.safety.verifier import VerifierState
from backend.storage.models import ObservationTable, UserProfileTable

from .context_builder import ContextBuilderService, UserStateSummary
from .response_composer import ResponseComposer
from .tool_executors import CarePathToolExecutors
from .tool_router import CarePathToolRouter
from .workflow import CarePathWorkflow, ToolCall, WorkflowState

_SYNTHETIC_CONTEXT_FLAGS = ("synthetic_demo", "synthetic_data")


class ExternalEvidenceIndex(Protocol):
    def search(self, query: str, *, top_k: int = 5) -> tuple[ExternalEvidenceHit, ...]: ...


def _synthetic_context_end(session: Session, user_id: UUID) -> datetime | None:
    """Anchor explicit synthetic demos to their latest observation for reproducible windows."""

    profile = session.get(UserProfileTable, str(user_id))
    if profile is None or not any(
        profile.consent_flags.get(key, False) for key in _SYNTHETIC_CONTEXT_FLAGS
    ):
        return None
    latest = session.scalar(
        select(ObservationTable.observed_at)
        .where(ObservationTable.user_id == str(user_id))
        .order_by(ObservationTable.observed_at.desc())
        .limit(1)
    )
    if latest is None:
        return None
    if latest.tzinfo is None or latest.utcoffset() is None:
        return latest.replace(tzinfo=UTC)
    return latest.astimezone(UTC)


class _PatientRuntimeStore(InMemoryRetrievalStore):
    def __init__(self, session: Session, summary_ref: dict[str, UserStateSummary]) -> None:
        super().__init__(RetrievalNamespace.PERSONAL)
        self.session = session
        self.summary_ref = summary_ref
        self.latest_items: dict[str, PatientEvidenceItem] = {}
        self.security_summary: dict[str, object] = {
            "prompt_injection_detected": False,
            "blocked_evidence_ids": [],
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> tuple[RetrievalHit, ...]:
        if user_id is None:
            raise ValueError("personal retrieval requires user_id")
        summary = self.summary_ref.get("summary")
        end_at = summary.generated_at if summary is not None else datetime.now(UTC)
        response = PatientEvidenceService(self.session).retrieve(
            PatientEvidenceQuery(user_id=UUID(user_id), window_days=30, end_at=end_at)
        )
        ranked = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
        safe_items: dict[str, PatientEvidenceItem] = {}
        blocked: list[str] = []
        for item in response.items:
            sanitized = sanitize_retrieved_content(item.fact)
            if not sanitized.allow_as_evidence:
                blocked.append(item.evidence_id)
                continue
            safe_item = item.model_copy(update={"fact": sanitized.content})
            safe_items[item.evidence_id] = safe_item
            ranked.add(
                RetrievalDocument(
                    evidence_id=item.evidence_id,
                    namespace=RetrievalNamespace.PERSONAL,
                    content=sanitized.render_untrusted_packet(),
                    user_id=user_id,
                    metadata=(
                        ("kind", item.kind.value),
                        ("trust", "untrusted_natural_language_data"),
                    ),
                )
            )
        self.latest_items = safe_items
        self.security_summary = {
            "prompt_injection_detected": bool(blocked),
            "blocked_evidence_ids": blocked,
        }
        hits = ranked.search(query, top_k=top_k, user_id=user_id)
        if hits:
            return hits
        return tuple(
            RetrievalHit(
                evidence_id=item.evidence_id,
                namespace=RetrievalNamespace.PERSONAL,
                content=sanitize_retrieved_content(item.fact).render_untrusted_packet(),
                score=0.0,
                user_id=user_id,
                metadata=(
                    ("kind", item.kind.value),
                    ("trust", "untrusted_natural_language_data"),
                ),
            )
            for item in safe_items.values()
        )[:top_k]


class _ExternalRuntimeStore(InMemoryRetrievalStore):
    def __init__(self, index: ExternalEvidenceIndex | None) -> None:
        super().__init__(RetrievalNamespace.EXTERNAL)
        self.index = index
        self.latest_hits: dict[str, ExternalEvidenceHit] = {}
        self.security_summary: dict[str, object] = {
            "prompt_injection_detected": False,
            "blocked_evidence_ids": [],
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> tuple[RetrievalHit, ...]:
        del user_id
        if self.index is None:
            self.latest_hits = {}
            self.security_summary = {
                "prompt_injection_detected": False,
                "blocked_evidence_ids": [],
            }
            return ()
        try:
            hits = self.index.search(query, top_k=top_k)
        except Exception:
            self.latest_hits = {}
            self.security_summary = {
                "prompt_injection_detected": False,
                "blocked_evidence_ids": [],
            }
            return ()

        safe_hits: dict[str, ExternalEvidenceHit] = {}
        blocked: list[str] = []
        result: list[RetrievalHit] = []
        for hit in hits:
            evidence_id = f"external:{hit.chunk_id}"
            sanitized = sanitize_retrieved_content(hit.content)
            if not sanitized.allow_as_evidence:
                blocked.append(evidence_id)
                continue
            safe_hit = hit.model_copy(update={"content": sanitized.content})
            safe_hits[evidence_id] = safe_hit
            result.append(
                RetrievalHit(
                    evidence_id=evidence_id,
                    namespace=RetrievalNamespace.EXTERNAL,
                    content=sanitized.render_untrusted_packet(),
                    score=hit.score,
                    source_id=hit.metadata.source_id,
                    metadata=(("trust", "untrusted_natural_language_data"),),
                )
            )
        self.latest_hits = safe_hits
        self.security_summary = {
            "prompt_injection_detected": bool(blocked),
            "blocked_evidence_ids": blocked,
        }
        return tuple(result)


def build_runtime_workflow(
    *,
    session: Session,
    user_id: UUID,
    request_text: str,
    external_index: ExternalEvidenceIndex | None = None,
    language: str = "en",
) -> CarePathWorkflow:
    """Wire real context, routing, retrieval, planner, verifier, and final Composer."""

    summary_ref: dict[str, UserStateSummary] = {}
    plan_ref: dict[str, PersonalizedWeeklyPlan] = {}
    evidence_ref: dict[str, EvidenceBundle] = {}
    context_end_at = _synthetic_context_end(session, user_id)
    personal_store = _PatientRuntimeStore(session, summary_ref)
    external_store = _ExternalRuntimeStore(external_index)
    retriever = DualRetriever(personal_store, external_store)
    router = CarePathToolRouter()
    planner = PersonalizedInterventionPlanner()
    aggregator = EvidenceAggregator()
    verifier = StrictGroundingSafetyVerifier()
    composer = ResponseComposer()

    def search_external(query: str, top_k: int) -> tuple[ExternalEvidenceHit, ...]:
        if external_index is None:
            return ()
        try:
            hits = external_index.search(query, top_k=top_k)
        except Exception:
            return ()
        safe_hits: list[ExternalEvidenceHit] = []
        for hit in hits:
            sanitized = sanitize_retrieved_content(hit.content)
            if sanitized.allow_as_evidence:
                safe_hits.append(hit.model_copy(update={"content": sanitized.content}))
        return tuple(safe_hits)

    tool_executors = CarePathToolExecutors(
        session,
        external_search=search_external,
    ).mapping()

    def context_builder(_: WorkflowState) -> dict[str, object]:
        summary = ContextBuilderService(session).build(user_id, end_at=context_end_at)
        summary_ref["summary"] = summary
        payload = summary.model_dump(mode="json")
        activity_constraints = summary.constraints.get("activity_constraints")
        if activity_constraints is not None:
            payload["activity_constraints"] = activity_constraints
        return payload

    def tool_router(_: WorkflowState) -> tuple[ToolCall, ...]:
        summary = summary_ref["summary"]
        return router.route(
            user_id=user_id,
            question=request_text,
            end_date=summary.generated_at.date(),
        ).calls

    def plan(state: WorkflowState) -> dict[str, object]:
        summary = summary_ref["summary"]
        patient_items = tuple(
            personal_store.latest_items[item.evidence_id]
            for item in state.personal_evidence
            if item.evidence_id in personal_store.latest_items
        )
        external_hits = tuple(
            external_store.latest_hits[item.evidence_id]
            for item in state.external_evidence
            if item.evidence_id in external_store.latest_hits
        )
        evidence = aggregator.build(patient_items=patient_items, external_hits=external_hits)
        weekly = planner.plan(
            summary=summary,
            evidence=evidence,
            start_date=summary.generated_at.date(),
            request_text=request_text,
            language=language,
        )
        plan_ref["plan"] = weekly
        evidence_ref["bundle"] = evidence
        injection_detected = bool(
            personal_store.security_summary["prompt_injection_detected"]
            or external_store.security_summary["prompt_injection_detected"]
        )
        state.context["prompt_injection_detected"] = injection_detected
        state.context["retrieval_security"] = {
            "personal": personal_store.security_summary,
            "external": external_store.security_summary,
        }
        draft = weekly.model_dump(mode="json")
        draft["risk_level"] = state.risk_level.value if state.risk_level is not None else "routine"
        external_ids = {
            item.evidence_id
            for item in evidence.external_evidence
            if item.evidence_id in weekly.evidence_ids
        }
        draft["claims"] = (
            [
                {
                    "claim_id": "plan-guidance",
                    "kind": "general_health",
                    "statement": weekly.actions[0].description,
                    "evidence_ids": sorted(external_ids),
                }
            ]
            if external_ids
            else []
        )
        return draft

    def compose(state: WorkflowState) -> str:
        summary = summary_ref["summary"]
        weekly = plan_ref["plan"]
        evidence = evidence_ref["bundle"]
        risk_level = state.risk_level
        if risk_level is None:
            raise ValueError("response composition requires a risk level")
        response = composer.compose(
            summary=summary,
            plan=weekly,
            evidence=evidence,
            risk_level=risk_level,
            language=language,
            prompt_injection_detected=bool(state.context.get("prompt_injection_detected")),
        )
        state.context["structured_response"] = response.model_dump(mode="json")
        return response.rendered_text

    return CarePathWorkflow(
        context_builder=context_builder,
        tool_router=tool_router,
        tool_executors=tool_executors,
        retriever=retriever,
        planner=plan,
        verifier=lambda state: verifier(cast(VerifierState, state)),
        composer=compose,
    )
