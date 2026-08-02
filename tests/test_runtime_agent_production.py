from __future__ import annotations

from uuid import UUID, uuid5

from backend.agents.runtime import build_runtime_workflow
from backend.agents.workflow import WorkflowState
from backend.evaluation.complete_models import BenchmarkRequest
from backend.evaluation.complete_scenarios import load_complete_scenarios
from backend.evaluation.runtime_agent_production_runner import RuntimeAgentBaselineRunner
from backend.evaluation.runtime_agent_runner import _EvaluationExternalIndex

_EVALUATION_NAMESPACE = UUID("83f2aa49-233c-4425-83da-5ed2be166670")


def test_production_agent_adapter_runs_without_hidden_exception() -> None:
    scenario = load_complete_scenarios()[0].scenario
    request = BenchmarkRequest.from_scenario(scenario)
    runner = RuntimeAgentBaselineRunner(deterministic_latency=True)
    user_id = uuid5(_EVALUATION_NAMESPACE, f"user:{request.scenario_id}")
    interaction_id = uuid5(_EVALUATION_NAMESPACE, f"interaction:{request.scenario_id}")

    runner._seed_user(request, user_id)
    runtime_text = runner._runtime_request_text(request)
    workflow = build_runtime_workflow(
        session=runner.session,
        user_id=user_id,
        request_text=runtime_text,
        external_index=_EvaluationExternalIndex(request),
        language=request.language.value,
    )
    state = workflow.run(
        WorkflowState(
            interaction_id=str(interaction_id),
            user_id=str(user_id),
            request_text=runtime_text,
        )
    )

    assert state.visited_nodes
    assert state.visited_nodes[0].value == "safety_triage"
