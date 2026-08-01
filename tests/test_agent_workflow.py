import json

import pytest

from backend.agents import (
    CarePathWorkflow,
    ToolCall,
    VerificationDisposition,
    WorkflowConfig,
    WorkflowNode,
    WorkflowState,
    WorkflowStatus,
)
from backend.retrieval import (
    DualRetriever,
    InMemoryRetrievalStore,
    RetrievalDocument,
    RetrievalNamespace,
)


def _retriever() -> DualRetriever:
    personal = InMemoryRetrievalStore(RetrievalNamespace.PERSONAL)
    external = InMemoryRetrievalStore(RetrievalNamespace.EXTERNAL)
    personal.add(
        RetrievalDocument(
            evidence_id="personal:journal:j-1",
            namespace=RetrievalNamespace.PERSONAL,
            content="My sleep schedule has been irregular this week.",
            user_id="user-a",
        )
    )
    personal.add(
        RetrievalDocument(
            evidence_id="personal:journal:j-other",
            namespace=RetrievalNamespace.PERSONAL,
            content="My sleep schedule has also been irregular.",
            user_id="user-b",
        )
    )
    external.add(
        RetrievalDocument(
            evidence_id="external:chunk-sleep",
            namespace=RetrievalNamespace.EXTERNAL,
            content="A regular sleep schedule can support healthy sleep habits.",
            source_id="src-sleep",
        )
    )
    return DualRetriever(personal, external)


def _successful_workflow(**overrides):
    defaults = {
        "context_builder": lambda state: {"request": state.request_text, "days": 7},
        "tool_router": lambda state: [
            ToolCall(call_id="trend-1", tool_name="trend", arguments={"days": 7})
        ],
        "tool_executors": {"trend": lambda arguments: {"direction": "stable", **arguments}},
        "retriever": _retriever(),
        "planner": lambda state: {
            "duration_days": 7,
            "goal": "restore a regular sleep routine",
            "evidence_count": len(state.personal_evidence) + len(state.external_evidence),
        },
        "verifier": lambda state: VerificationDisposition.PASS,
        "composer": lambda state: f"Verified plan: {state.draft['goal']}",
    }
    defaults.update(overrides)
    return CarePathWorkflow(**defaults)


def _state(request_text: str = "Help me make my sleep schedule more regular") -> WorkflowState:
    return WorkflowState(
        interaction_id="interaction-1",
        user_id="user-a",
        request_text=request_text,
    )


def test_all_frozen_nodes_are_visited_on_success():
    state = _successful_workflow().run(_state())

    assert state.status is WorkflowStatus.COMPLETED
    assert state.visited_nodes == [
        WorkflowNode.SAFETY_TRIAGE,
        WorkflowNode.CONTEXT_BUILDER,
        WorkflowNode.TOOL_ROUTER,
        WorkflowNode.ANALYTICS_TOOLS,
        WorkflowNode.PERSONAL_CONTEXT_RETRIEVER,
        WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER,
        WorkflowNode.PLANNER,
        WorkflowNode.VERIFIER,
        WorkflowNode.COMPOSER,
        WorkflowNode.FEEDBACK_UPDATE,
    ]
    assert state.tool_results["trend-1"] == {"direction": "stable", "days": 7}
    assert state.personal_evidence[0].evidence_id == "personal:journal:j-1"
    assert state.external_evidence[0].evidence_id == "external:chunk-sleep"
    assert "j-other" not in {item.evidence_id for item in state.personal_evidence}


def test_workflow_state_round_trips_json():
    state = _successful_workflow().run(_state())

    serialized = state.model_dump_json()
    restored = WorkflowState.model_validate_json(serialized)

    assert restored.model_dump(mode="json") == state.model_dump(mode="json")
    assert json.loads(serialized)["status"] == "completed"


def test_verifier_regeneration_is_bounded_to_one():
    planner_calls = 0
    verifier_calls = 0

    def planner(state):
        nonlocal planner_calls
        planner_calls += 1
        return {"attempt": planner_calls}

    def verifier(state):
        nonlocal verifier_calls
        verifier_calls += 1
        return VerificationDisposition.REGENERATE_ONCE

    workflow = _successful_workflow(planner=planner, verifier=verifier)
    state = workflow.run(_state())

    assert planner_calls == 2
    assert verifier_calls == 2
    assert state.regeneration_count == 1
    assert state.verification_disposition is VerificationDisposition.FALLBACK
    assert state.status is WorkflowStatus.BLOCKED
    assert state.visited_nodes.count(WorkflowNode.PLANNER) == 2
    assert state.visited_nodes.count(WorkflowNode.VERIFIER) == 2


def test_workflow_config_rejects_unbounded_regeneration():
    with pytest.raises(ValueError):
        WorkflowConfig(max_regenerations=2)


def test_tool_failure_retries_are_bounded_and_response_is_controlled():
    attempts = 0

    def failing_tool(arguments):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("private raw payload should never escape")

    workflow = _successful_workflow(
        tool_executors={"trend": failing_tool},
        config=WorkflowConfig(max_tool_attempts=2),
    )
    state = workflow.run(_state())

    assert attempts == 2
    assert state.status is WorkflowStatus.FAILED
    assert state.failures[-1].code == "tool_execution_failed"
    assert state.failures[-1].attempts == 2
    assert "private raw payload" not in state.model_dump_json()
    assert "no coaching plan was generated" in state.response_text
    assert WorkflowNode.PLANNER not in state.visited_nodes


def test_unknown_tool_is_rejected_before_execution():
    workflow = _successful_workflow(
        tool_router=lambda state: [ToolCall(call_id="unknown-1", tool_name="unknown", arguments={})]
    )
    state = workflow.run(_state())

    assert state.status is WorkflowStatus.FAILED
    assert state.failures[-1].code == "tool_not_allow_listed"
    assert WorkflowNode.ANALYTICS_TOOLS not in state.visited_nodes
    assert WorkflowNode.PLANNER not in state.visited_nodes


def test_urgent_safety_result_bypasses_context_tools_and_planner():
    called = {"context": 0, "planner": 0, "composer": 0}

    def context_builder(state):
        called["context"] += 1
        return {}

    def planner(state):
        called["planner"] += 1
        return {}

    def composer(state):
        called["composer"] += 1
        return "ordinary plan"

    workflow = _successful_workflow(
        context_builder=context_builder,
        planner=planner,
        composer=composer,
    )
    state = workflow.run(_state("I cannot breathe"))

    assert state.status is WorkflowStatus.BLOCKED
    assert state.visited_nodes == [
        WorkflowNode.SAFETY_TRIAGE,
        WorkflowNode.COMPOSER,
        WorkflowNode.FEEDBACK_UPDATE,
    ]
    assert called == {"context": 0, "planner": 0, "composer": 0}
    assert "local emergency services" in state.response_text
    assert state.draft is None


def test_caution_respects_deterministic_planning_gate():
    planner_calls = 0

    def planner(state):
        nonlocal planner_calls
        planner_calls += 1
        return {"goal": "should not run"}

    workflow = _successful_workflow(planner=planner)
    state = workflow.run(_state("Do I have depression?"))

    assert state.risk_level.value == "caution"
    assert state.allow_normal_planning is False
    assert state.status is WorkflowStatus.BLOCKED
    assert planner_calls == 0
    assert WorkflowNode.PLANNER not in state.visited_nodes


def test_verifier_exception_uses_fail_safe_fallback_without_raw_error():
    def verifier(state):
        raise RuntimeError("sensitive verifier payload")

    state = _successful_workflow(verifier=verifier).run(_state())

    assert state.status is WorkflowStatus.BLOCKED
    assert state.verification_disposition is VerificationDisposition.FALLBACK
    assert state.failures[-1].code == "verifier_failed"
    assert "sensitive verifier payload" not in state.model_dump_json()
    assert "could not verify" in state.response_text
