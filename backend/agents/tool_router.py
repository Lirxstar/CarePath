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
    MISSINGNESS = "missingness"
    ADHERENCE_SUMMARY = "adherence_summary"
    USER_HISTORY = "user_history"
    GUIDELINE_RETRIEVAL = "guideline_retrieval"


class MetricToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    metric_type: MetricType
    days: int = Field(default=7, ge=1, le=30)
    end_date: date


class MissingnessToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    days: int = Field(default=30, ge=7, le=30)
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
    ToolName.MISSINGNESS: MissingnessToolArguments,
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
    MetricType.SLEEP_DURATION: (
        "sleep duration",
        "hours slept",
        "how long did i sleep",
        "睡眠时长",
        "睡了多久",
        "睡眠時間",
    ),
    MetricType.SLEEP_START_TIME: (
        "bedtime",
        "fall asleep",
        "go to bed",
        "sleep start",
        "when do i sleep",
        "入睡",
        "就寝",
    ),
    MetricType.SLEEP_END_TIME: (
        "wake time",
        "wake up",
        "sleep end",
        "起床",
        "醒来",
    ),
    MetricType.STEPS: ("step", "steps", "walk", "walking", "步数", "走", "歩"),
    MetricType.ACTIVE_MINUTES: ("active minute", "activity", "exercise", "运动", "活動", "運動"),
    MetricType.RESTING_HEART_RATE: ("resting heart", "heart rate", "心率", "心拍"),
    MetricType.STRESS_SCORE: ("stress", "workload", "压力", "ストレス", "負担"),
    MetricType.MOOD_SCORE: ("mood", "low energy", "情绪", "心情", "気分"),
    MetricType.ACTIVITY_CONFIDENCE: (
        "confidence walking",
        "walking confidence",
        "balance",
        "unsteady",
        "信心",
        "平衡",
        "ふらつ",
    ),
}
_DIRECTIONAL_CHANGE_TERMS = (
    "change",
    "changed",
    "worse",
    "better",
    "increase",
    "decrease",
    "gotten better",
    "gotten worse",
    "变化",
    "变差",
    "改善",
    "変化",
    "悪化",
)
_COMPARE_TERMS = (
    "compared",
    "compare",
    "versus",
    "than before",
    "preceding",
    "previous period",
    "baseline",
    "weekend",
    "工作日",
    "周末",
    "相比",
    "比较",
    "前一周",
    "以前",
    "比較",
    "前週",
    "平日",
    "週末",
)
_ABRUPT_CHANGE_TERMS = (
    "sudden",
    "abrupt",
    "outlier",
    "spike",
    "drop",
    "45,000",
    "异常",
    "突变",
    "急に",
    "外れ値",
)
_TREND_TERMS = (
    "trend",
    "recent",
    "last week",
    "last month",
    "7 day",
    "30 day",
    "stable",
    "irregular",
    "regular",
    "regularly",
    "increasing",
    "decreasing",
    "improving",
    "最近",
    "趋势",
    "稳定",
    "不规律",
    "傾向",
    "安定",
    "この一週間",
)
_MISSINGNESS_TERMS = (
    "missing",
    "missingness",
    "gap",
    "blank",
    "drop out",
    "incomplete data",
    "suspect",
    "quality flag",
    "缺失",
    "空白",
    "数据质量",
    "欠損",
    "データ不足",
)
_ADHERENCE_TERMS = (
    "adherence",
    "completed",
    "completion",
    "rejected",
    "reject",
    "keep missing",
    "make it easier",
    "plan version",
    "没完成",
    "拒绝",
    "完成率",
    "未達成",
    "拒否",
    "もっと簡単",
)
_PLAN_TERMS = (
    "plan",
    "routine",
    "goal",
    "action",
    "schedule",
    "change the plan",
    "计划",
    "目标",
    "行动",
    "習慣",
    "目標",
    "プラン",
)
_GUIDANCE_TERMS = (
    "recommend",
    "suggest",
    "what should",
    "what can",
    "how can",
    "should i",
    "guideline",
    "advice",
    "focus on",
    "建议",
    "推荐",
    "指南",
    "怎么",
    "如何",
    "おすすめ",
    "推奨",
    "どうすれば",
)
_HISTORY_TERMS = (
    "history",
    "last month",
    "previous plan",
    "plan version",
    "journal",
    "日记",
    "历史",
    "履歴",
    "日誌",
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
        wants_missingness = any(term in text for term in _MISSINGNESS_TERMS)
        explicit_plan = any(term in text for term in _PLAN_TERMS)
        wants_adherence = explicit_plan or any(term in text for term in _ADHERENCE_TERMS)
        wants_plan = explicit_plan or wants_adherence
        wants_history = wants_plan or any(term in text for term in _HISTORY_TERMS)
        wants_guidance = wants_plan or any(term in text for term in _GUIDANCE_TERMS)
        wants_directional_change = (
            any(term in text for term in _DIRECTIONAL_CHANGE_TERMS) and not wants_plan
        )
        wants_compare = any(term in text for term in _COMPARE_TERMS)
        wants_abrupt_change = any(term in text for term in _ABRUPT_CHANGE_TERMS)
        wants_trend = (
            wants_directional_change
            or wants_compare
            or wants_abrupt_change
            or any(term in text for term in _TREND_TERMS)
        )
        calls: list[ToolCall] = []

        for metric in metrics[:2]:
            if wants_directional_change:
                calls.extend(
                    [
                        self._metric_call(ToolName.TREND, user_id, metric, end_date),
                        self._metric_call(ToolName.WINDOW_COMPARISON, user_id, metric, end_date),
                        self._metric_call(ToolName.CHANGE_DETECTION, user_id, metric, end_date),
                    ]
                )
            elif wants_compare:
                calls.append(
                    self._metric_call(ToolName.WINDOW_COMPARISON, user_id, metric, end_date)
                )
            elif wants_abrupt_change:
                calls.append(
                    self._metric_call(ToolName.CHANGE_DETECTION, user_id, metric, end_date)
                )
            elif wants_trend or wants_plan:
                calls.append(self._metric_call(ToolName.TREND, user_id, metric, end_date))

        if wants_missingness:
            calls.append(
                ToolCall(
                    call_id="missingness",
                    tool_name=ToolName.MISSINGNESS.value,
                    arguments={
                        "user_id": str(user_id),
                        "days": 30,
                        "end_date": end_date.isoformat(),
                    },
                )
            )
        if wants_adherence:
            calls.append(
                ToolCall(
                    call_id="adherence",
                    tool_name=ToolName.ADHERENCE_SUMMARY.value,
                    arguments={"user_id": str(user_id), "recent_days": 7},
                )
            )
        if wants_history:
            calls.append(
                ToolCall(
                    call_id="history",
                    tool_name=ToolName.USER_HISTORY.value,
                    arguments={"user_id": str(user_id), "window_days": 30},
                )
            )
        if wants_guidance:
            calls.append(
                ToolCall(
                    call_id="guideline",
                    tool_name=ToolName.GUIDELINE_RETRIEVAL.value,
                    arguments={"query": question[:500], "top_k": 5},
                )
            )
        if not calls and metrics:
            calls.append(self._metric_call(ToolName.TREND, user_id, metrics[0], end_date))
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
        metrics = [
            metric for metric, terms in _METRIC_TERMS.items() if any(term in text for term in terms)
        ]
        sleep_metrics = {
            MetricType.SLEEP_DURATION,
            MetricType.SLEEP_START_TIME,
            MetricType.SLEEP_END_TIME,
        }
        if not any(metric in sleep_metrics for metric in metrics) and any(
            term in text for term in ("sleep", "slept", "睡眠", "睡", "眠")
        ):
            metrics.insert(0, MetricType.SLEEP_DURATION)
        if "when do i sleep" in text:
            if MetricType.SLEEP_START_TIME not in metrics:
                metrics.insert(0, MetricType.SLEEP_START_TIME)
            if MetricType.SLEEP_END_TIME not in metrics:
                metrics.append(MetricType.SLEEP_END_TIME)
        return metrics

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
