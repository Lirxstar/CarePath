from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents import CarePathWorkflow, ToolCall, VerificationDisposition, WorkflowState
from backend.audit import build_workflow_audit, persist_workflow_audit
from backend.retrieval import (
    DualRetriever,
    InMemoryRetrievalStore,
    RetrievalDocument,
    RetrievalNamespace,
)
from backend.storage.models import AuditEventTable, InteractionTable, UserProfileTable


def _workflow(user_id: str) -> CarePathWorkflow:
    personal = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
    personal.add(
        RetrievalDocument(
            evidence_id="personal:journal:j-1",
            namespace=RetrievalNamespace.PERSONAL,
            content="PRIVATE JOURNAL TEXT must not enter audit output",
            user_id=user_id,
        )
    )
    external = InMemoryRetrievalStore(RetrievalNamespace.EXTERNAL)
    external.add(
        RetrievalDocument(
            evidence_id="external:chunk-1",
            namespace=RetrievalNamespace.EXTERNAL,
            content="PRIVATE GUIDELINE CONTENT must not be copied",
            source_id="source-1",
        )
    )
    verifier_calls = 0

    def verifier(state: WorkflowState) -> VerificationDisposition:
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 1:
            return VerificationDisposition.REGENERATE_ONCE
        return VerificationDisposition.PASS

    return CarePathWorkflow(
        context_builder=lambda state: {
            "journal_text": "PRIVATE CONTEXT TEXT",
            "api_key": "sk-private-context-value",
        },
        tool_router=lambda state: [
            ToolCall(
                call_id="trend-1",
                tool_name="trend",
                arguments={"days": 7, "raw_note": "PRIVATE TOOL ARGUMENT"},
            )
        ],
        tool_executors={
            "trend": lambda arguments: {
                "direction": "stable",
                "private_result": "PRIVATE TOOL RESULT",
                **arguments,
            }
        },
        retriever=DualRetriever(personal, external),
        planner=lambda state: {
            "attempt": state.regeneration_count + 1,
            "private_draft": "PRIVATE MODEL DRAFT",
        },
        verifier=verifier,
        composer=lambda state: "PRIVATE FINAL RESPONSE",
    )


def _run_state() -> WorkflowState:
    user_id = str(uuid4())
    interaction_id = str(uuid4())
    return _workflow(user_id).run(
        WorkflowState(
            interaction_id=interaction_id,
            user_id=user_id,
            request_text="PRIVATE USER REQUEST",
        )
    )


def test_audit_trace_preserves_workflow_order_and_minimises_raw_text() -> None:
    state = _run_state()
    events = build_workflow_audit(state, created_at=datetime(2026, 7, 30, 7, 0, tzinfo=UTC))

    assert [event.sequence_number for event in events] == list(range(1, 11))
    assert [event.event_type.value for event in events] == [
        "safety_decision",
        "tool_call",
        "tool_result",
        "retrieval",
        "retrieval",
        "plan_generated",
        "verification",
        "plan_revised",
        "verification",
        "response_emitted",
    ]
    verification_events = [event for event in events if event.event_type.value == "verification"]
    assert [event.output_summary["disposition"] for event in verification_events] == [
        "regenerate_once",
        "pass",
    ]
    assert events[1].input_refs == {
        "call_id": "trend-1",
        "tool_name": "trend",
        "argument_keys": ["days", "raw_note"],
    }
    assert events[3].input_refs["evidence_ids"] == ["personal:journal:j-1"]
    assert events[4].input_refs["evidence_ids"] == ["external:chunk-1"]
    assert events[4].input_refs["source_ids"] == ["source-1"]

    serialized = json.dumps([event.model_dump(mode="json") for event in events], sort_keys=True)
    for raw_secret in (
        "PRIVATE USER REQUEST",
        "PRIVATE JOURNAL TEXT",
        "PRIVATE CONTEXT TEXT",
        "sk-private-context-value",
        "PRIVATE TOOL ARGUMENT",
        "PRIVATE TOOL RESULT",
        "PRIVATE GUIDELINE CONTENT",
        "PRIVATE MODEL DRAFT",
        "PRIVATE FINAL RESPONSE",
    ):
        assert raw_secret not in serialized


def test_persisted_audit_is_ordered_and_immutable(database_session: Session) -> None:
    state = _run_state()
    now = datetime(2026, 7, 30, 7, 30, tzinfo=UTC)
    database_session.add(
        UserProfileTable(
            user_id=state.user_id,
            age_band="30-44",
            preferred_language="en",
            timezone="UTC",
            schedule_constraints=None,
            health_goals=["sleep"],
            activity_constraints=None,
            coaching_preferences=None,
            consent_flags={"demo": True},
        )
    )
    database_session.flush()
    database_session.add(
        InteractionTable(
            interaction_id=state.interaction_id,
            user_id=state.user_id,
            request_text=state.request_text,
            language="en",
            started_at=now,
            completed_at=now,
            risk_level="routine",
            final_status="completed",
            response_json={"status": "completed"},
        )
    )
    database_session.flush()

    persisted = persist_workflow_audit(database_session, state, created_at=now)
    rows = database_session.scalars(
        select(AuditEventTable)
        .where(AuditEventTable.interaction_id == state.interaction_id)
        .order_by(AuditEventTable.sequence_number.asc())
    ).all()

    assert len(rows) == len(persisted) == 10
    assert [row.sequence_number for row in rows] == list(range(1, 11))
    assert [row.event_type for row in rows] == [event.event_type.value for event in persisted]
    with pytest.raises(ValueError, match="already exist"):
        persist_workflow_audit(database_session, state, created_at=now)
