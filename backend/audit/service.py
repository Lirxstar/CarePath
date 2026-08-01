"""Privacy-minimised workflow audit trail construction and persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents import VerificationDisposition, WorkflowNode, WorkflowState
from backend.domain import AuditEvent
from backend.domain.models import AuditEventType
from backend.storage.models import AuditEventTable, InteractionTable


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("audit timestamps must include a timezone")
    return timestamp.astimezone(UTC)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, str)]


def _verification_entries(state: WorkflowState) -> list[Mapping[str, object]]:
    trace = state.context.get("audit_trace")
    if not isinstance(trace, Sequence) or isinstance(trace, (str, bytes, bytearray)):
        return []
    entries: list[Mapping[str, object]] = []
    for item in trace:
        if not isinstance(item, Mapping) or item.get("event_type") != "verification":
            continue
        entries.append(item)
    return entries


def _safe_verification_summary(
    entry: Mapping[str, object] | None,
    disposition: VerificationDisposition,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "disposition": disposition.value,
        "verification_passed": disposition is VerificationDisposition.PASS,
    }
    if entry is None:
        return summary
    raw = entry.get("output_summary")
    if not isinstance(raw, Mapping):
        return summary

    failed_rule_ids = _string_list(raw.get("failed_rule_ids"))
    if failed_rule_ids:
        summary["failed_rule_ids"] = failed_rule_ids
    risk_level = raw.get("risk_level")
    if isinstance(risk_level, str) and risk_level in {"routine", "caution", "urgent"}:
        summary["risk_level"] = risk_level
    prompt_injection_detected = raw.get("prompt_injection_detected")
    if isinstance(prompt_injection_detected, bool):
        summary["prompt_injection_detected"] = prompt_injection_detected
    return summary


def _verification_dispositions(state: WorkflowState, count: int) -> list[VerificationDisposition]:
    entries = _verification_entries(state)
    dispositions: list[VerificationDisposition] = []
    for entry in entries[:count]:
        raw = entry.get("output_summary")
        if not isinstance(raw, Mapping):
            break
        status = raw.get("status")
        if not isinstance(status, str):
            break
        try:
            dispositions.append(VerificationDisposition(status))
        except ValueError:
            break

    while len(dispositions) < count:
        index = len(dispositions)
        if count > 1 and index == 0:
            dispositions.append(VerificationDisposition.REGENERATE_ONCE)
            continue
        dispositions.append(state.verification_disposition or VerificationDisposition.FALLBACK)
    return dispositions


def _evidence_refs(state: WorkflowState, *, external: bool) -> dict[str, object]:
    evidence = state.external_evidence if external else state.personal_evidence
    refs: dict[str, object] = {
        "namespace": "external" if external else "personal",
        "evidence_ids": [item.evidence_id for item in evidence],
    }
    source_ids = sorted({item.source_id for item in evidence if item.source_id is not None})
    if source_ids:
        refs["source_ids"] = source_ids
    return refs


def _failure_codes(state: WorkflowState, component: str) -> list[str]:
    return [failure.code for failure in state.failures if failure.component == component]


def build_workflow_audit(
    state: WorkflowState,
    *,
    created_at: datetime | None = None,
) -> list[AuditEvent]:
    """Build an ordered reviewer trace without copying raw user/model content.

    The builder intentionally stores references, counts, booleans, enum values and
    controlled failure codes only. Request text, journal text, tool arguments/results,
    draft text and response text are never copied into an audit event.
    """

    timestamp = _utc_timestamp(created_at)
    interaction_id = UUID(state.interaction_id)
    verification_entries = _verification_entries(state)
    verification_count = state.visited_nodes.count(WorkflowNode.VERIFIER)
    verification_dispositions = _verification_dispositions(state, verification_count)
    verifier_index = 0
    planner_attempt = 0
    events: list[AuditEvent] = []

    def append(
        event_type: AuditEventType,
        component: str,
        input_refs: dict[str, object],
        output_summary: dict[str, object],
    ) -> None:
        events.append(
            AuditEvent(
                audit_event_id=uuid4(),
                interaction_id=interaction_id,
                sequence_number=len(events) + 1,
                event_type=event_type,
                component=component,
                input_refs=input_refs,
                output_summary=output_summary,
                created_at=timestamp,
            )
        )

    for node in state.visited_nodes:
        if node is WorkflowNode.SAFETY_TRIAGE:
            append(
                AuditEventType.SAFETY_DECISION,
                node.value,
                {"interaction_id": state.interaction_id},
                {
                    "risk_level": state.risk_level.value if state.risk_level is not None else None,
                    "matched_rule_ids": list(state.matched_rule_ids),
                    "policy_flags": list(state.policy_flags),
                    "allow_normal_planning": state.allow_normal_planning,
                    "uncertainty_present": state.uncertainty_reason is not None,
                },
            )
            continue

        if node is WorkflowNode.ANALYTICS_TOOLS:
            if not state.tool_calls:
                append(
                    AuditEventType.TOOL_RESULT,
                    node.value,
                    {"tool_call_ids": []},
                    {"attempted_tools": 0, "successful_tools": 0},
                )
                continue
            for call in state.tool_calls:
                append(
                    AuditEventType.TOOL_CALL,
                    call.tool_name,
                    {
                        "call_id": call.call_id,
                        "tool_name": call.tool_name,
                        "argument_keys": sorted(call.arguments),
                    },
                    {"selected": True},
                )
                succeeded = call.call_id in state.tool_results
                result = state.tool_results.get(call.call_id)
                result_summary: dict[str, object] = {
                    "status": "success" if succeeded else "failed",
                    "result_type": type(result).__name__ if succeeded else None,
                }
                failure_codes = _failure_codes(state, call.tool_name)
                if failure_codes:
                    result_summary["failure_codes"] = failure_codes
                append(
                    AuditEventType.TOOL_RESULT,
                    call.tool_name,
                    {"call_id": call.call_id, "tool_name": call.tool_name},
                    result_summary,
                )
            continue

        if node is WorkflowNode.PERSONAL_CONTEXT_RETRIEVER:
            failure_codes = _failure_codes(state, node.value)
            append(
                AuditEventType.RETRIEVAL,
                node.value,
                _evidence_refs(state, external=False),
                {
                    "status": "failed" if failure_codes else "success",
                    "retrieval_count": len(state.personal_evidence),
                    "failure_codes": failure_codes,
                },
            )
            continue

        if node is WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER:
            failure_codes = _failure_codes(state, node.value)
            append(
                AuditEventType.RETRIEVAL,
                node.value,
                _evidence_refs(state, external=True),
                {
                    "status": "failed" if failure_codes else "success",
                    "retrieval_count": len(state.external_evidence),
                    "failure_codes": failure_codes,
                },
            )
            continue

        if node is WorkflowNode.PLANNER:
            planner_attempt += 1
            append(
                AuditEventType.PLAN_GENERATED
                if planner_attempt == 1
                else AuditEventType.PLAN_REVISED,
                node.value,
                {
                    "draft_attempt": planner_attempt,
                    "personal_evidence_ids": [item.evidence_id for item in state.personal_evidence],
                    "external_evidence_ids": [item.evidence_id for item in state.external_evidence],
                    "tool_call_ids": [call.call_id for call in state.tool_calls],
                },
                {
                    "status": "generated" if planner_attempt == 1 else "revised",
                    "draft_present": state.draft is not None,
                },
            )
            continue

        if node is WorkflowNode.VERIFIER:
            disposition = verification_dispositions[verifier_index]
            entry = (
                verification_entries[verifier_index]
                if verifier_index < len(verification_entries)
                else None
            )
            verifier_index += 1
            append(
                AuditEventType.VERIFICATION,
                node.value,
                {
                    "draft_attempt": verifier_index,
                    "personal_evidence_ids": [item.evidence_id for item in state.personal_evidence],
                    "external_evidence_ids": [item.evidence_id for item in state.external_evidence],
                    "tool_call_ids": [call.call_id for call in state.tool_calls],
                },
                _safe_verification_summary(entry, disposition),
            )
            continue

        if node is WorkflowNode.COMPOSER:
            append(
                AuditEventType.RESPONSE_EMITTED,
                node.value,
                {"interaction_id": state.interaction_id},
                {
                    "status": state.status.value,
                    "risk_level": state.risk_level.value if state.risk_level is not None else None,
                    "verification_disposition": (
                        state.verification_disposition.value
                        if state.verification_disposition is not None
                        else None
                    ),
                    "response_present": state.response_text is not None,
                    "failure_codes": [failure.code for failure in state.failures],
                },
            )

    return events


def persist_workflow_audit(
    session: Session,
    state: WorkflowState,
    *,
    created_at: datetime | None = None,
) -> list[AuditEvent]:
    """Persist one immutable ordered audit trace for an existing interaction."""

    if session.get(InteractionTable, state.interaction_id) is None:
        raise ValueError("interaction must be persisted before audit events")
    existing = session.scalar(
        select(AuditEventTable.audit_event_id)
        .where(AuditEventTable.interaction_id == state.interaction_id)
        .limit(1)
    )
    if existing is not None:
        raise ValueError("audit events already exist for this interaction")

    events = build_workflow_audit(state, created_at=created_at)
    session.add_all(
        [
            AuditEventTable(
                audit_event_id=str(event.audit_event_id),
                interaction_id=str(event.interaction_id),
                sequence_number=event.sequence_number,
                event_type=event.event_type.value,
                component=event.component,
                input_refs=event.input_refs,
                output_summary=event.output_summary,
                created_at=event.created_at,
            )
            for event in events
        ]
    )
    session.flush()
    return events
