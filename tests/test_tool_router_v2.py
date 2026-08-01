from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from backend.agents.tool_router import CarePathToolRouter, execute_tool_calls
from backend.agents.workflow import ToolCall


def test_tool_router_selection_accuracy_is_measurable() -> None:
    cases = json.loads(
        Path("data/evaluation/cp054_tool_routing_cases.json").read_text(encoding="utf-8")
    )
    router = CarePathToolRouter()
    user_id = uuid4()
    correct = 0

    for case in cases:
        decision = router.route(
            user_id=user_id,
            question=case["question"],
            end_date=date(2026, 7, 30),
        )
        selected = [call.tool_name for call in decision.calls]
        if selected == case["expected_tools"]:
            correct += 1

    accuracy = correct / len(cases)
    assert accuracy >= 0.9


def test_tool_router_validates_user_metric_top_k_limits_and_duplicates() -> None:
    router = CarePathToolRouter(max_calls=4)
    user_id = uuid4()
    other_user = uuid4()

    with pytest.raises(ValueError):
        router.validate_calls(
            (
                ToolCall(
                    call_id="wrong-user",
                    tool_name="trend",
                    arguments={
                        "user_id": str(other_user),
                        "metric_type": "steps",
                        "days": 7,
                        "end_date": "2026-07-30",
                    },
                ),
            ),
            expected_user_id=user_id,
        )

    with pytest.raises(ValueError):
        router.validate_calls(
            (
                ToolCall(
                    call_id="bad-metric",
                    tool_name="trend",
                    arguments={
                        "user_id": str(user_id),
                        "metric_type": "blood_pressure",
                        "days": 7,
                        "end_date": "2026-07-30",
                    },
                ),
            ),
            expected_user_id=user_id,
        )

    with pytest.raises(ValueError):
        router.validate_calls(
            (
                ToolCall(
                    call_id="bad-k",
                    tool_name="guideline_retrieval",
                    arguments={"query": "sleep", "top_k": 11},
                ),
            ),
            expected_user_id=user_id,
        )

    duplicate = ToolCall(
        call_id="duplicate",
        tool_name="trend",
        arguments={
            "user_id": str(user_id),
            "metric_type": "steps",
            "days": 7,
            "end_date": "2026-07-30",
        },
    )
    with pytest.raises(ValueError, match="duplicate tool call"):
        router.validate_calls((duplicate, duplicate), expected_user_id=user_id)

    with pytest.raises(ValueError, match="tool call limit"):
        router.validate_calls(
            tuple(
                ToolCall(
                    call_id=f"call-{index}",
                    tool_name="guideline_retrieval",
                    arguments={"query": f"sleep {index}", "top_k": 3},
                )
                for index in range(5)
            ),
            expected_user_id=user_id,
        )


def test_tool_router_records_no_tool_and_execution_fallback() -> None:
    user_id = uuid4()
    router = CarePathToolRouter()
    no_tool = router.route(
        user_id=user_id,
        question="Hello, thank you",
        end_date=date(2026, 7, 30),
    )
    assert no_tool.no_tool_required is True
    assert no_tool.calls == ()

    routed = router.route(
        user_id=user_id,
        question="Show my sleep trend",
        end_date=date(2026, 7, 30),
    )

    def fail(_: object) -> object:
        raise RuntimeError("synthetic failure")

    outcomes = execute_tool_calls(routed, {"trend": fail})
    assert len(outcomes) == 1
    assert outcomes[0].succeeded is False
    assert outcomes[0].fallback_message == "tool_execution_failed"
