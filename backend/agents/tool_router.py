"""Structured, bounded tool selection and validation for CarePath."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.domain.models import MetricType

from .workflow import ToolCall

MAX_TOOL_CALLS = 4


class ToolName(StrEnum):
    TREND = "trend"
    WINDOW_COMPARISON = "window_comparison"
    CHANGE_DETECTION = "change_detection"
    ADHERENCE_SUMMARY = "adherence_summary"
    USER_HISTORY = "user_history"
    GUIDELINE_RETRIEVAL = "guideline_retrieval"


class MetricToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    metric_type: MetricType
    days: int = Field(default=7, ge=1, le=30)
    end_date: date


class AdherenceToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    recent_days: int = Field(default=7, ge=1, le=30)


class UserHistoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    window_days: int = Field(default=30, ge=7, le=30)
    keyword: str | None = Field(default=None, min_length=1, max_length=200)


class GuidelineRetrievalArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


_ARGUMENT_MODEL: dict[ToolName, type[BaseModel]] = {
    ToolName.TREND: MetricToolArguments,
    ToolName.WINDOW_COMPARISON: MetricToolArguments,
    ToolName.CHANGE_DETECTION: MetricToolArguments,
    ToolName.ADHERENCE_SUMMARY: AdherenceToolArguments,
    ToolName.USER_HISTORY: UserHistoryArguments,
    ToolName.GUIDELINE_RETRIEVAL: GuidelineRetrievalArguments,
}


class ToolRoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calls: tuple[ToolCall, ...]
    no_tool_required: bool
    reason: str


class ToolExecutionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    call_id: str
    tool_name: ToolName
    succeeded: bool
    result: Any = None
    fallback_message: str | None = None


ToolFunction = Callable[[Mapping[str, Any]], Any]

_METRIC_TERMS: dict[MetricType, tuple[str, ...]] = {
    MetricType.SLEEP_DURATION: ("sleep", "slept", "睡眠", "睡", "眠"),
    MetricType.STEPS: ("step", "steps", "walk", "walking", "步数", "走", "歩"),
    MetricType.ACTIVE_MINUTES: ("active minute", "activity", "exercise", "运动", "活動", "運動"),
    MetricType.RESTING_HEART_RATE: ("resting heart", "heart rate", "心率", "心拍"),
    MetricType.STRESS_SCORE: ("stress", "压力", "ストレス", "負担"),
    MetricType.MOOD_SCORE: ("mood", "情绪", "心情", "気分"),
}
_CHANGE_TERMS = (
    "change",
    "changed",
    "worse",
    "better",
    "increase",
    "decrease",
    "变化",
    "变差",
    "改善",
    "変化",
    "悪化",
    "改善",
)
_TREND_TERMS = (
    "trend",
    "recent",
    "last week",
    "7 day",
    "30 day",
    "最近",
    "趋势",
    "傾向",
    "この一週間",
)
_PLAN_TERMS = (
    "plan",
    "routine",
    "goal",
    "action",
    "schedule",
    "计划",
    "目标",
    "行动",
    "習慣",
    "目標",
    "プラン",
)
_GUIDANCE_TERMS = (
    "recommend",
    "should i",
    "guideline",
    "advice",
    "建议",
    "推荐",
    "指南",
    "おすすめ",
    "推奨",
)
_NO_TOOL_TERMS = ("hello", "hi", "thanks", "thank you", "你好", "谢谢", "こんにちは", "ありがとう")


class CarePathToolRouter:
    """Choose the smallest validated tool set for one request."""

    def __init__(self, *, max_calls: int = MAX_TOOL_CALLS) -> None:
        if not 1 <= max_calls <= MAX_TOOL_CALLS:
            raise ValueError(f"max_calls must be between 1 and {MAX_TOOL_CALLS}")
        self.max_calls = max_calls

    def route(self, *, user_id: UUID, question: str, end_date: date) -> ToolRoutingDecision:
        text = " ".join(question.casefold().split())
        if not text:
            raise ValueError("question must not be empty")
        if any(term in text for term in _NO_TOOL_TERMS) and not self._metrics(text):
            return ToolRoutingDecision(
                calls=(), no_tool_required=True, reason="conversational_request"
            )

        metrics = self._metrics(text)
        wants_change = any(term in text for term in _CHANGE_TERMS)
        wants_trend = wants_change or any(term in text for term in _TREND_TERMS)
        wants_plan = any(term in text for term in _PLAN_TERMS)
        wants_guidance = wants_plan or any(term in text for term in _GUIDANCE_TERMS)
        calls: list[ToolCall] = []

        for metric in metrics[:2]:
            if wants_trend or wants_plan:
                calls.append(self._metric_call(ToolName.TREND, user_id, metric, end_date))
            if wants_change:
                calls.append(
                    self._metric_call(ToolName.WINDOW_COMPARISON, user_id, metric, end_date)
                )
                calls.append(
                    self._metric_call(ToolName.CHANGE_DETECTION, user_id, metric, end_date)
                )

        if wants_plan:
            calls.extend(
                [
                    ToolCall(
                        call_id="adherence",
                        tool_name=ToolName.ADHERENCE_SUMMARY.value,
                        arguments={"user_id": str(user_id), "recent_days": 7},
                    ),
                    ToolCall(
                        call_id="history",
                        tool_name=ToolName.USER_HISTORY.value,
                        arguments={"user_id": str(user_id), "window_days": 30},
                    ),
                ]
            )
        if wants_guidance:
            calls.append(
                ToolCall(
                    call_id="guideline",
                    tool_name=ToolName.GUIDELINE_RETRIEVAL.value,
                    arguments={"query": question, "top_k": 5},
                )
            )
        if not calls and metrics:
            metric = metrics[0]
            calls.append(self._metric_call(ToolName.TREND, user_id, metric, end_date))
        if not calls:
            return ToolRoutingDecision(calls=(), no_tool_required=True, reason="no_analysis_needed")

        validated = self.validate_calls(tuple(calls[: self.max_calls]), expected_user_id=user_id)
        return ToolRoutingDecision(
            calls=validated,
            no_tool_required=False,
            reason="minimal_required_tools",
        )

    def validate_calls(
        self, calls: tuple[ToolCall, ...], *, expected_user_id: UUID
    ) -> tuple[ToolCall, ...]:
        if len(calls) > self.max_calls:
            raise ValueError("tool call limit exceeded")
        validated: list[ToolCall] = []
        signatures: set[str] = set()
        for call in calls:
            try:
                tool = ToolName(call.tool_name)
            except ValueError as exc:
                raise ValueError(f"unknown tool: {call.tool_name}") from exc
            model_type = _ARGUMENT_MODEL[tool]
            arguments = TypeAdapter(model_type).validate_python(call.arguments)
            dumped = arguments.model_dump(mode="json")
            supplied_user = dumped.get("user_id")
            if supplied_user is not None and supplied_user != str(expected_user_id):
                raise ValueError("tool user_id does not match workflow user")
            signature = f"{tool.value}:{json.dumps(dumped, sort_keys=True, separators=(',', ':'))}"
            if signature in signatures:
                raise ValueError("duplicate tool call rejected to prevent routing loops")
            signatures.add(signature)
            validated.append(ToolCall(call_id=call.call_id, tool_name=tool.value, arguments=dumped))
        return tuple(validated)

    @staticmethod
    def _metrics(text: str) -> list[MetricType]:
        return [
            metric for metric, terms in _METRIC_TERMS.items() if any(term in text for term in terms)
        ]

    @staticmethod
    def _metric_call(tool: ToolName, user_id: UUID, metric: MetricType, end_date: date) -> ToolCall:
        return ToolCall(
            call_id=f"{tool.value}:{metric.value}",
            tool_name=tool.value,
            arguments={
                "user_id": str(user_id),
                "metric_type": metric.value,
                "days": 7,
                "end_date": end_date.isoformat(),
            },
        )


def execute_tool_calls(
    decision: ToolRoutingDecision,
    executors: Mapping[str, ToolFunction],
) -> tuple[ToolExecutionOutcome, ...]:
    """Execute a validated route with controlled per-tool degradation."""

    outcomes: list[ToolExecutionOutcome] = []
    for call in decision.calls:
        tool = ToolName(call.tool_name)
        executor = executors.get(tool.value)
        if executor is None:
            outcomes.append(
                ToolExecutionOutcome(
                    call_id=call.call_id,
                    tool_name=tool,
                    succeeded=False,
                    fallback_message="tool_unavailable",
                )
            )
            continue
        try:
            result = executor(call.arguments)
        except Exception:
            outcomes.append(
                ToolExecutionOutcome(
                    call_id=call.call_id,
                    tool_name=tool,
                    succeeded=False,
                    fallback_message="tool_execution_failed",
                )
            )
        else:
            outcomes.append(
                ToolExecutionOutcome(
                    call_id=call.call_id,
                    tool_name=tool,
                    succeeded=True,
                    result=result,
                )
            )
    return tuple(outcomes)
