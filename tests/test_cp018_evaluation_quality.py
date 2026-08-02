from __future__ import annotations

from datetime import date
from string import hexdigits
from uuid import uuid4

from backend.agents.tool_router import CarePathToolRouter
from backend.evaluation.complete_metrics import score_output
from backend.evaluation.complete_models import BenchmarkRequest, CompleteBaselineOutput
from backend.evaluation.fixture_builder import build_evaluation_fixture
from backend.evaluation.harness import BaselineId
from backend.evaluation.runtime_agent_valid_fixture_runner import RuntimeAgentBaselineRunner
from backend.evaluation.scenarios import SafetyOutcome, load_scenario_set


def _scenario(scenario_id: str):
    return next(item for item in load_scenario_set().scenarios if item.scenario_id == scenario_id)


def test_fixture_partitions_every_stable_evidence_reference() -> None:
    for scenario in load_scenario_set().scenarios:
        fixture = build_evaluation_fixture(scenario)
        reconstructed = {
            *fixture.observation_refs,
            *fixture.journal_refs,
            *fixture.profile_refs,
            *fixture.plan_refs,
            *fixture.feedback_refs,
            *fixture.event_refs,
            *fixture.quality_refs,
        }
        assert reconstructed == set(scenario.expected_evidence.personal)
        assert fixture.external_evidence_refs == scenario.expected_evidence.external
        assert fixture.context_text


def test_nonroutine_scenarios_are_not_scored_as_failed_retrieval() -> None:
    scenario = _scenario("CP016-SF-001")
    output = CompleteBaselineOutput(
        baseline_id=BaselineId.B3_CAREPATH_AGENT,
        scenario_id=scenario.scenario_id,
        response_text="Controlled urgent response.",
        safety_outcome=SafetyOutcome.URGENT,
        ttft_ms=1.0,
        total_latency_ms=1.0,
    )

    metrics = score_output(scenario, output)

    assert metrics.retrieval_applicable is False
    assert metrics.tool_routing_applicable is False
    assert metrics.citation_applicable is False


def test_production_runner_uses_scenario_aligned_evidence() -> None:
    scenario = _scenario("CP016-RT-001")
    runner = RuntimeAgentBaselineRunner(deterministic_latency=True)

    output = runner.run(BenchmarkRequest.from_scenario(scenario))

    assert output.status.value == "completed"
    actual = {hit.evidence_ref for hit in output.retrieval_hits}
    assert set(scenario.expected_evidence.external) <= actual
    assert len(set(scenario.expected_evidence.personal) & actual) >= 2
    assert not any(
        ref.startswith("profile:")
        and len(ref.split(":", 1)[-1]) == 12
        and all(character in hexdigits for character in ref.split(":", 1)[-1])
        for ref in actual
    )
    assert output.raw_evidence_count >= output.unmapped_evidence_count


def test_router_covers_missingness_adherence_and_multilingual_trends() -> None:
    router = CarePathToolRouter()
    user_id = uuid4()
    end_date = date(2026, 7, 30)

    missing = router.route(
        user_id=user_id,
        question="There are missing gaps in my sleep data.",
        end_date=end_date,
    )
    assert [call.tool_name for call in missing.calls] == ["missingness"]

    adherence = router.route(
        user_id=user_id,
        question="I rejected the evening walk. Can you change the plan?",
        end_date=end_date,
    )
    assert [call.tool_name for call in adherence.calls] == [
        "trend",
        "adherence_summary",
        "user_history",
        "guideline_retrieval",
    ]

    sleep_timing = router.route(
        user_id=user_id,
        question="When do I sleep most regularly?",
        end_date=end_date,
    )
    assert [call.arguments["metric_type"] for call in sleep_timing.calls] == [
        "sleep_start_time",
        "sleep_end_time",
    ]

    japanese = router.route(
        user_id=user_id,
        question="最近の睡眠傾向を教えてください",
        end_date=end_date,
    )
    assert [call.tool_name for call in japanese.calls] == ["trend"]
