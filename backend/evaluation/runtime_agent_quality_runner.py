from __future__ import annotations

from uuid import UUID, uuid5

from backend.storage.models import ObservationTable

from .complete_models import BenchmarkRequest
from .fixture_builder import EvaluationFixture
from .runtime_agent_production_runner import (
    RuntimeAgentBaselineRunner as _AlignedRuntimeAgentBaselineRunner,
    _EVENT_METRICS,
    _UNIT_BY_METRIC,
)
from .runtime_agent_runner import _EVALUATION_END, _EVALUATION_NAMESPACE


class RuntimeAgentBaselineRunner(_AlignedRuntimeAgentBaselineRunner):
    """Aligned B3 runner with domain-valid synthetic time-series values."""

    def _seed_observations(
        self,
        request: BenchmarkRequest,
        fixture: EvaluationFixture,
        user_id: UUID,
    ) -> None:
        metric_refs = {ref.split(":", 1)[1]: ref for ref in fixture.observation_refs}
        metric_refs.update({ref.split(":", 1)[1]: ref for ref in fixture.event_refs})
        for quality_ref in fixture.quality_refs:
            metric = quality_ref.split(":", 1)[1]
            metric_refs.setdefault(metric, f"observation:{metric}")
        if not metric_refs:
            metric_refs["sleep_duration"] = "observation:sleep_duration"

        text = f"{request.user_question} {fixture.context_text}".casefold()
        missing = any(
            term in text
            for term in ("missing", "gap", "blank", "drop out", "缺失", "欠損")
        )
        suspect = any(
            term in text
            for term in ("45,000", "suspect", "outlier", "异常", "外れ値")
        )
        for index in range(30):
            if missing and 10 <= index <= 15:
                continue
            observed_at = _EVALUATION_END.replace() - __import__("datetime").timedelta(
                days=29 - index
            )
            for metric, reference in sorted(metric_refs.items()):
                observation_id = str(
                    uuid5(
                        _EVALUATION_NAMESPACE,
                        f"observation:{request.scenario_id}:{metric}:{index}",
                    )
                )
                is_event = metric in _EVENT_METRICS
                quality = "suspect" if suspect and index == 26 else "valid"
                numeric, boolean = _quality_fixture_value(metric, index, text)
                if suspect and metric == "steps" and index == 26:
                    numeric = 45000.0
                self.session.add(
                    ObservationTable(
                        observation_id=observation_id,
                        user_id=str(user_id),
                        metric_type=metric,
                        value_numeric=None if is_event else numeric,
                        value_boolean=boolean if is_event else None,
                        unit=None if is_event else _UNIT_BY_METRIC.get(metric, "score_1_10"),
                        observed_at=observed_at,
                        source_type="synthetic_wearable",
                        quality_flag=quality,
                        confidence=0.95,
                        metadata_json={
                            "scenario_id": request.scenario_id,
                            "evidence_ref": reference,
                        },
                    )
                )
                refs = [reference]
                refs.extend(
                    ref
                    for ref in fixture.quality_refs
                    if ref.split(":", 1)[1] == metric and quality == "suspect"
                )
                self._register(observation_id, *refs)


def _quality_fixture_value(
    metric: str,
    index: int,
    text: str,
) -> tuple[float | None, bool | None]:
    recent = index >= 23
    improving = any(
        term in text for term in ("improving", "upward", "increase", "恢复", "改善")
    )
    declining = any(
        term in text for term in ("shorter", "decrease", "lower", "reduced", "下降")
    )
    if metric in _EVENT_METRICS:
        positive = any(
            term in text for term in ("fall recorded", "near-fall", "nearly fallen")
        )
        negated = any(term in text for term in ("no fall", "have not fallen", "没有跌倒"))
        return None, bool(positive and not negated and index >= 26)

    base = {
        "sleep_duration": 7.2,
        "sleep_start_time": 1380.0,
        "sleep_end_time": 420.0,
        "sleep_quality": 7.0,
        "steps": 6200.0,
        "active_minutes": 28.0,
        "resting_heart_rate": 65.0,
        "stress_score": 5.0,
        "mood_score": 6.5,
        "activity_confidence": 7.5,
    }.get(metric, 5.0)
    delta = 0.0
    if recent:
        direction = 1.0 if improving else -1.0 if declining else 0.0
        if metric in {"stress_score", "resting_heart_rate"}:
            direction *= -1.0
        scale = 700.0 if metric == "steps" else 4.0 if metric == "active_minutes" else 0.8
        delta = direction * scale
    if metric == "sleep_start_time" and any(
        term in text for term in ("varies", "irregular")
    ):
        delta += float((index % 3) * 75)
    if metric == "sleep_end_time" and any(
        term in text for term in ("varies", "irregular")
    ):
        delta += float((index % 3) * 60)

    value = float(base + delta)
    if metric in {"sleep_start_time", "sleep_end_time"}:
        value %= 1440.0
    return value, None
