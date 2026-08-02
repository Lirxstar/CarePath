from __future__ import annotations

from pathlib import Path


path = Path("backend/agents/tool_router.py")
text = path.read_text(encoding="utf-8")

anchor = '''        if any(term in question_text for term in _NO_TOOL_TERMS) and not self._metrics(
            analysis_text
        ):
            return ToolRoutingDecision(
                calls=(), no_tool_required=True, reason="conversational_request"
            )

        metrics = self._metrics(analysis_text)
'''
replacement = '''        if any(term in question_text for term in _NO_TOOL_TERMS) and not self._metrics(
            analysis_text
        ):
            return ToolRoutingDecision(
                calls=(), no_tool_required=True, reason="conversational_request"
            )
        if not separator:
            direct = self._route_direct_contract(
                user_id=user_id,
                question=question,
                text=question_text,
                end_date=end_date,
            )
            if direct is not None:
                return direct

        metrics = self._metrics(analysis_text)
'''
if anchor not in text:
    raise RuntimeError("direct compatibility insertion anchor missing")
text = text.replace(anchor, replacement, 1)

method_anchor = '''    def validate_calls(
        self, calls: tuple[ToolCall, ...], *, expected_user_id: UUID
    ) -> tuple[ToolCall, ...]:
'''
method = '''    def _route_direct_contract(
        self,
        *,
        user_id: UUID,
        question: str,
        text: str,
        end_date: date,
    ) -> ToolRoutingDecision | None:
        """Preserve the stable direct-call contract used by the API and CP-054."""

        metrics = self._metrics(text)
        metric = metrics[0] if metrics else MetricType.SLEEP_DURATION
        planning_request = (
            any(term in text for term in _PLAN_TERMS)
            or ("recommend" in text and "routine" in text)
            or (
                any(term in text for term in ("build", "make", "help me"))
                and any(term in text for term in ("routine", "schedule", "regular"))
            )
        )
        directional_request = any(term in text for term in _DIRECTIONAL_CHANGE_TERMS)
        guideline_request = any(term in text for term in ("guideline", "guidelines", "指南"))
        trend_request = any(term in text for term in _TREND_TERMS)

        calls: list[ToolCall]
        if planning_request:
            calls = [
                self._metric_call(ToolName.TREND, user_id, metric, end_date),
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
                ToolCall(
                    call_id="guideline",
                    tool_name=ToolName.GUIDELINE_RETRIEVAL.value,
                    arguments={"query": question[:500], "top_k": 5},
                ),
            ]
        elif directional_request:
            calls = [
                self._metric_call(ToolName.TREND, user_id, metric, end_date),
                self._metric_call(ToolName.WINDOW_COMPARISON, user_id, metric, end_date),
                self._metric_call(ToolName.CHANGE_DETECTION, user_id, metric, end_date),
            ]
        elif guideline_request:
            calls = [
                ToolCall(
                    call_id="guideline",
                    tool_name=ToolName.GUIDELINE_RETRIEVAL.value,
                    arguments={"query": question[:500], "top_k": 5},
                )
            ]
        elif trend_request:
            calls = [self._metric_call(ToolName.TREND, user_id, metric, end_date)]
        else:
            return None

        validated = self.validate_calls(
            tuple(calls[: self.max_calls]), expected_user_id=user_id
        )
        return ToolRoutingDecision(
            calls=validated,
            no_tool_required=False,
            reason="stable_direct_contract",
        )

    def validate_calls(
        self, calls: tuple[ToolCall, ...], *, expected_user_id: UUID
    ) -> tuple[ToolCall, ...]:
'''
if method_anchor not in text:
    raise RuntimeError("direct compatibility method anchor missing")
text = text.replace(method_anchor, method, 1)
path.write_text(text, encoding="utf-8")
Path(__file__).unlink()
