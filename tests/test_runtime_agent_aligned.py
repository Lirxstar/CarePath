from __future__ import annotations

from time import perf_counter_ns
from uuid import UUID, uuid5

from backend.agents.context_builder import ContextBuilderService
from backend.agents.runtime import build_runtime_workflow
from backend.agents.workflow import WorkflowState
from backend.evaluation.complete_models import BenchmarkRequest, SecurityDisposition
from backend.evaluation.fixture_builder import fixture_for_scenario
from backend.evaluation.runtime_agent_production_runner import (
    RuntimeAgentBaselineRunner,
    _AlignedEvaluationExternalIndex,
)
from backend.evaluation.runtime_agent_runner import _EVALUATION_END
from backend.evaluation.scenarios import ScenarioCategory, load_scenario_set

_EVALUATION_NAMESPACE = UUID("83f2aa49-233c-4425-83da-5ed2be166670")


def test_aligned_production_runner_has_no_hidden_exception() -> None:
    scenario = next(
        item for item in load_scenario_set().scenarios if item.scenario_id == "CP016-RT-001"
    )
    request = BenchmarkRequest.from_scenario(scenario)
    fixture = fixture_for_scenario(request.scenario_id)
    runner = RuntimeAgentBaselineRunner(deterministic_latency=True)
    user_id = uuid5(_EVALUATION_NAMESPACE, f"user:{request.scenario_id}")
    interaction_id = uuid5(_EVALUATION_NAMESPACE, f"interaction:{request.scenario_id}")

    runner._seed_user(request, user_id)
    summary = ContextBuilderService(runner.session).build(user_id, end_at=_EVALUATION_END)
    assert summary.user_id == user_id

    runtime_text = runner._runtime_request_text(request)
    workflow = build_runtime_workflow(
        session=runner.session,
        user_id=user_id,
        request_text=runtime_text,
        external_index=_AlignedEvaluationExternalIndex(request, fixture),
        language=request.language.value,
    )
    started = perf_counter_ns()
    state = workflow.run(
        WorkflowState(
            interaction_id=str(interaction_id),
            user_id=str(user_id),
            request_text=runtime_text,
        )
    )
    assert state.status.value == "completed", state.failures

    output = runner._aligned_output(
        request,
        fixture,
        state,
        user_id,
        (perf_counter_ns() - started) / 1_000_000,
    )

    assert output.status.value == "completed"
    assert output.visited_nodes[0] == "safety_triage"


def test_all_fixed_scenarios_complete_and_reject_hostile_documents() -> None:
    runner = RuntimeAgentBaselineRunner(deterministic_latency=True)
    failures: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    hostile_failures: list[tuple[str, str, tuple[str, ...]]] = []

    for scenario in load_scenario_set().scenarios:
        output = runner.run(BenchmarkRequest.from_scenario(scenario))
        if output.status.value == "failed":
            failures.append((scenario.scenario_id, output.error_codes, output.visited_nodes))
        if (
            scenario.category is ScenarioCategory.HOSTILE_DOCUMENT
            and output.security_disposition is not SecurityDisposition.REJECTED
        ):
            hostile_failures.append(
                (
                    scenario.scenario_id,
                    output.security_disposition.value,
                    output.visited_nodes,
                )
            )

    assert not failures, failures
    assert not hostile_failures, hostile_failures
