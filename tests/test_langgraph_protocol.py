from __future__ import annotations

from uuid import uuid4

from backend.agents import (
    AgentGraphState,
    AgentNodeInput,
    AgentNodeOutput,
    NodeResultStatus,
    VerificationDisposition,
    WorkflowNode,
    build_carepath_langgraph,
    default_safety_handler,
    passthrough_handler,
)


def _handlers() -> dict[WorkflowNode, object]:
    planner_calls = 0
    verifier_calls = 0

    def analytics(node_input: AgentNodeInput) -> AgentNodeOutput:
        return AgentNodeOutput(
            state=node_input.state,
            record_ids=("obs-1", "obs-2"),
            tool_parameters={
                "window_days": 7,
                "metric_type": "steps",
                "raw_note": "PRIVATE TOOL ARGUMENT",
            },
        )

    def planner(node_input: AgentNodeInput) -> AgentNodeOutput:
        nonlocal planner_calls
        planner_calls += 1
        return AgentNodeOutput(
            state=node_input.state.model_copy(
                update={"plan_draft": {"attempt": planner_calls, "action_count": 1}}
            ),
            document_ids=("external:chunk-1",),
        )

    def verifier(node_input: AgentNodeInput) -> AgentNodeOutput:
        nonlocal verifier_calls
        verifier_calls += 1
        disposition = (
            VerificationDisposition.REGENERATE_ONCE
            if verifier_calls == 1
            else VerificationDisposition.PASS
        )
        return AgentNodeOutput(
            state=node_input.state.model_copy(update={"verification_result": disposition})
        )

    def composer(node_input: AgentNodeInput) -> AgentNodeOutput:
        return AgentNodeOutput(
            state=node_input.state.model_copy(update={"final_response": "bounded response"})
        )

    handlers = dict.fromkeys(WorkflowNode, passthrough_handler)
    handlers[WorkflowNode.SAFETY_TRIAGE] = default_safety_handler()
    handlers[WorkflowNode.ANALYTICS_TOOLS] = analytics
    handlers[WorkflowNode.PLANNER] = planner
    handlers[WorkflowNode.VERIFIER] = verifier
    handlers[WorkflowNode.COMPOSER] = composer
    return handlers


def test_langgraph_executes_typed_nodes_with_one_bounded_regeneration() -> None:
    graph = build_carepath_langgraph(_handlers())  # type: ignore[arg-type]
    initial = AgentGraphState(
        interaction_id=str(uuid4()),
        user_id=str(uuid4()),
        request_text="Help me build a regular walking routine",
        model_provider="mock",
    )

    result = AgentGraphState.model_validate(graph.invoke(initial.model_dump(mode="python")))

    assert result.final_response == "bounded response"
    assert result.verification_result is VerificationDisposition.PASS
    assert result.retry_count == 1
    assert [event.node_name for event in result.node_audit_events] == [
        WorkflowNode.SAFETY_TRIAGE,
        WorkflowNode.CONTEXT_BUILDER,
        WorkflowNode.TOOL_ROUTER,
        WorkflowNode.ANALYTICS_TOOLS,
        WorkflowNode.PERSONAL_CONTEXT_RETRIEVER,
        WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER,
        WorkflowNode.PLANNER,
        WorkflowNode.VERIFIER,
        WorkflowNode.PLANNER,
        WorkflowNode.VERIFIER,
        WorkflowNode.COMPOSER,
        WorkflowNode.FEEDBACK_UPDATE,
    ]
    assert all(event.started_at <= event.finished_at for event in result.node_audit_events)
    assert all(event.model_provider == "mock" for event in result.node_audit_events)
    analytics = next(
        event
        for event in result.node_audit_events
        if event.node_name is WorkflowNode.ANALYTICS_TOOLS
    )
    assert analytics.record_ids == ("obs-1", "obs-2")
    assert analytics.tool_parameters == {"window_days": 7, "metric_type": "steps"}
    assert "PRIVATE TOOL ARGUMENT" not in result.model_dump_json()


def test_langgraph_state_round_trips_and_audit_omits_request_text() -> None:
    graph = build_carepath_langgraph(_handlers())  # type: ignore[arg-type]
    secret_request = "PRIVATE REQUEST TEXT must not be copied into node audit"
    result = AgentGraphState.model_validate(
        graph.invoke(
            AgentGraphState(
                interaction_id=str(uuid4()),
                user_id=str(uuid4()),
                request_text=secret_request,
                model_provider="mock",
            ).model_dump(mode="python")
        )
    )

    round_trip = AgentGraphState.model_validate_json(result.model_dump_json())
    assert round_trip == result
    audit_json = "".join(event.model_dump_json() for event in result.node_audit_events)
    assert secret_request not in audit_json
    assert all(
        event.input_summary["interaction_id"] == result.interaction_id
        for event in result.node_audit_events
    )


def test_langgraph_safety_bypasses_planning_for_urgent_request() -> None:
    graph = build_carepath_langgraph(_handlers())  # type: ignore[arg-type]

    result = AgentGraphState.model_validate(
        graph.invoke(
            AgentGraphState(
                interaction_id=str(uuid4()),
                user_id=str(uuid4()),
                request_text="I cannot breathe",
                model_provider="mock",
            ).model_dump(mode="python")
        )
    )

    assert result.risk_assessment is not None
    assert result.risk_assessment.risk_level.value == "urgent"
    assert WorkflowNode.PLANNER not in [event.node_name for event in result.node_audit_events]
    assert [event.node_name for event in result.node_audit_events] == [
        WorkflowNode.SAFETY_TRIAGE,
        WorkflowNode.COMPOSER,
        WorkflowNode.FEEDBACK_UPDATE,
    ]


def test_langgraph_node_failure_becomes_controlled_error_state() -> None:
    handlers = _handlers()

    def broken_context(node_input: AgentNodeInput) -> AgentNodeOutput:
        del node_input
        raise RuntimeError("PRIVATE RAW FAILURE")

    handlers[WorkflowNode.CONTEXT_BUILDER] = broken_context
    graph = build_carepath_langgraph(handlers)  # type: ignore[arg-type]

    result = AgentGraphState.model_validate(
        graph.invoke(
            AgentGraphState(
                interaction_id=str(uuid4()),
                user_id=str(uuid4()),
                request_text="Help with walking",
                model_provider="mock",
            ).model_dump(mode="python")
        )
    )

    assert result.error_state is not None
    assert result.error_state.code == "context_builder_failed"
    assert NodeResultStatus.FAILED in {event.result_status for event in result.node_audit_events}
    assert "PRIVATE RAW FAILURE" not in result.model_dump_json()
