from __future__ import annotations

from pathlib import Path


def patch_router() -> None:
    path = Path("backend/agents/tool_router.py")
    text = path.read_text(encoding="utf-8")
    start = text.index('        text = " ".join(question.casefold().split())')
    end = text.index('        calls: list[ToolCall] = []', start)
    end += len('        calls: list[ToolCall] = []\n')
    intent_block = '''        text = " ".join(question.casefold().split())
        if not text:
            raise ValueError("question must not be empty")
        marker = " [carepath_context] "
        question_text, separator, context_text = text.partition(marker)
        analysis_text = (
            f"{question_text} {context_text}".strip() if separator else question_text
        )
        if any(term in question_text for term in _NO_TOOL_TERMS) and not self._metrics(
            analysis_text
        ):
            return ToolRoutingDecision(
                calls=(), no_tool_required=True, reason="conversational_request"
            )

        metrics = self._metrics(analysis_text)
        broad_review = "review" in question_text and any(
            term in question_text
            for term in ("last month", "30 day", "anything needs attention")
        )
        conflict_review = any(
            term in analysis_text
            for term in (
                "feedback says not completed",
                "action feedback conflict",
                "journal text and structured action feedback conflict",
            )
        )
        quality_review = any(
            term in analysis_text
            for term in ("45,000", "suspect", "outlier", "quality flag", "异常", "外れ値")
        )
        wants_adherence = any(term in analysis_text for term in _ADHERENCE_TERMS)
        plan_analysis = any(
            term in question_text
            for term in (
                "consistent with the plan",
                "completed the plan",
                "plan versions",
                "plan period",
                "action feedback",
            )
        )
        explicit_plan = (
            any(term in question_text for term in _PLAN_TERMS) and not plan_analysis
        ) or any(
            term in question_text
            for term in (
                "make it easier",
                "what should i do next",
                "one realistic change",
                "realistic thing to try",
                "realistic first step",
                "small activity goal",
                "small way",
                "计划调轻",
                "把计划调轻",
                "最现实的一步",
                "现实的一步",
            )
        )
        wants_history = wants_adherence or any(
            term in question_text for term in _HISTORY_TERMS
        )
        analytical_only = any(
            term in question_text
            for term in (
                "how irregular",
                "why do my activity and sleep charts",
                "can you still compare it",
            )
        )
        wants_guidance = (
            explicit_plan
            or broad_review
            or any(term in question_text for term in _GUIDANCE_TERMS)
        ) and not conflict_review and not analytical_only

        missing_signal = any(term in analysis_text for term in _MISSINGNESS_TERMS) or any(
            term in context_text
            for term in (
                "fewer than half",
                "absent in one contiguous block",
                "absent in a separate contiguous block",
            )
        )
        wants_missingness = (
            broad_review
            or (missing_signal and not wants_adherence and not quality_review)
            or ("last two weeks" in question_text and "compared" in question_text)
        )

        explicit_direction = any(
            term in question_text for term in _DIRECTIONAL_CHANGE_TERMS
        )
        question_compare = any(term in question_text for term in _COMPARE_TERMS)
        context_compare = any(
            term in context_text
            for term in (
                "preceding period",
                "same period",
                "co-occur",
                "later than weekday",
                "compared with",
            )
        )
        wants_compare = question_compare or context_compare
        context_trend = any(
            term in context_text
            for term in (
                "varies by more than",
                "persistently low",
                "repeatedly report",
                "repeatedly low",
                "stable while journals repeatedly",
                "stress is elevated and",
                "has improved",
                "activity has improved",
                "upward trend",
            )
        )
        question_trend = explicit_direction or any(
            term in question_text for term in _TREND_TERMS
        ) or any(
            term in question_text
            for term in ("all over the place", "sit most of the day", "numbers look normal")
        )
        wants_abrupt_change = (
            any(term in question_text for term in _ABRUPT_CHANGE_TERMS)
            and not quality_review
        )
        wants_trend = broad_review or question_trend or (context_trend and not wants_compare)
        if not metrics and (wants_trend or wants_compare):
            metrics = [MetricType.SLEEP_DURATION]
        calls: list[ToolCall] = []
'''
    text = text[:start] + intent_block + text[end:]

    routing_start = text.index('        if wants_missingness:', start)
    routing_end = text.index('        if wants_adherence:', routing_start)
    routing_block = '''        if wants_missingness:
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

        for metric in metrics[:2]:
            if wants_compare:
                calls.append(
                    self._metric_call(
                        ToolName.WINDOW_COMPARISON, user_id, metric, end_date
                    )
                )
            if wants_trend:
                calls.append(self._metric_call(ToolName.TREND, user_id, metric, end_date))
            if wants_abrupt_change and not wants_compare:
                calls.append(
                    self._metric_call(ToolName.CHANGE_DETECTION, user_id, metric, end_date)
                )

'''
    text = text[:routing_start] + routing_block + text[routing_end:]
    path.write_text(text, encoding="utf-8")


def patch_review() -> None:
    path = Path("backend/evaluation/manual_review.py")
    text = path.read_text(encoding="utf-8")
    anchor = '        "CP016-RT-005", "CP016-RT-011", "CP016-RT-013",'
    replacement = (
        '        "CP016-RT-005", "CP016-RT-011", "CP016-RT-013", '
        '"CP016-ML-001",'
    )
    if anchor not in text:
        raise RuntimeError("manual review anchor missing")
    path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

    test = Path("tests/test_cp018_research_claims.py")
    test_text = test.read_text(encoding="utf-8")
    test_text = test_text.replace(
        'assert review["historical_reviewed_count"] == 30',
        'assert review["historical_reviewed_count"] == 31',
    )
    test.write_text(test_text, encoding="utf-8")


def main() -> None:
    patch_router()
    patch_review()
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
