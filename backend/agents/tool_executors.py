"""Deterministic tool executors used by the validated CarePath router."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.models import MetricType, Observation, ObservationUnit, QualityFlag, SourceType
from backend.retrieval import ExternalEvidenceHit, PatientEvidenceQuery, PatientEvidenceService
from backend.storage.models import ObservationTable
from backend.timeseries import compare_periods, compute_change_signal, compute_trend
from backend.timeseries.config import UNIT_BY_METRIC

from .context_builder import ContextBuilderService
from .tool_router import (
    AdherenceToolArguments,
    GuidelineRetrievalArguments,
    MetricToolArguments,
    ToolName,
    UserHistoryArguments,
)

ExternalSearch = Callable[[str, int], tuple[ExternalEvidenceHit, ...]]


class CarePathToolExecutors:
    def __init__(self, session: Session, *, external_search: ExternalSearch | None = None) -> None:
        self.session = session
        self.external_search = external_search

    def mapping(self) -> Mapping[str, Callable[[Mapping[str, Any]], Any]]:
        raw: dict[ToolName, Callable[[Mapping[str, Any]], Any]] = {
            ToolName.TREND: self._trend,
            ToolName.WINDOW_COMPARISON: self._comparison,
            ToolName.CHANGE_DETECTION: self._change,
            ToolName.ADHERENCE_SUMMARY: self._adherence,
            ToolName.USER_HISTORY: self._history,
            ToolName.GUIDELINE_RETRIEVAL: self._guideline,
        }
        return {tool.value: self._safe(executor) for tool, executor in raw.items()}

    @staticmethod
    def _safe(
        executor: Callable[[Mapping[str, Any]], Any],
    ) -> Callable[[Mapping[str, Any]], Any]:
        def invoke(arguments: Mapping[str, Any]) -> Any:
            try:
                return executor(arguments)
            except Exception:
                return {"status": "unavailable", "reason": "tool_execution_failed"}

        return invoke

    def _trend(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        args = TypeAdapter(MetricToolArguments).validate_python(arguments)
        observations = self._metric_observations(
            args.user_id, args.metric_type, args.end_date, args.days
        )
        return compute_trend(
            observations,
            days=args.days,
            end_date=args.end_date,
            metric=args.metric_type,
        ).model_dump(mode="json")

    def _comparison(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        args = TypeAdapter(MetricToolArguments).validate_python(arguments)
        observations = self._metric_observations(
            args.user_id, args.metric_type, args.end_date, args.days * 2
        )
        return compare_periods(
            observations,
            end_date=args.end_date,
            window_days=args.days,
            metric=args.metric_type,
        ).model_dump(mode="json")

    def _change(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        args = TypeAdapter(MetricToolArguments).validate_python(arguments)
        observations = self._metric_observations(
            args.user_id, args.metric_type, args.end_date, args.days * 2
        )
        recent_start = args.end_date - timedelta(days=args.days - 1)
        baseline_end = recent_start - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=args.days - 1)
        current = [
            float(item.value_numeric)
            for item in observations
            if recent_start <= item.observed_at.date() <= args.end_date
            and item.quality_flag is QualityFlag.VALID
            and item.value_numeric is not None
        ]
        baseline = [
            float(item.value_numeric)
            for item in observations
            if baseline_start <= item.observed_at.date() <= baseline_end
            and item.quality_flag is QualityFlag.VALID
            and item.value_numeric is not None
        ]
        source_ids = tuple(
            item.observation_id
            for item in observations
            if baseline_start <= item.observed_at.date() <= args.end_date
        )
        return compute_change_signal(
            metric=args.metric_type,
            unit=UNIT_BY_METRIC[args.metric_type],
            start_date=recent_start,
            end_date=args.end_date,
            current_values=current,
            baseline_values=baseline,
            source_observation_ids=source_ids,
            expected_count=args.days,
        ).model_dump(mode="json")

    def _adherence(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        args = TypeAdapter(AdherenceToolArguments).validate_python(arguments)
        summary = ContextBuilderService(self.session).build(args.user_id)
        return summary.adherence.model_dump(mode="json")

    def _history(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        args = TypeAdapter(UserHistoryArguments).validate_python(arguments)
        result = PatientEvidenceService(self.session).retrieve(
            PatientEvidenceQuery(
                user_id=args.user_id,
                window_days=7 if args.window_days == 7 else 30,
                keyword=args.keyword,
            )
        )
        return result.model_dump(mode="json")

    def _guideline(self, arguments: Mapping[str, Any]) -> list[dict[str, object]]:
        args = TypeAdapter(GuidelineRetrievalArguments).validate_python(arguments)
        if self.external_search is None:
            return []
        return [hit.model_dump(mode="json") for hit in self.external_search(args.query, args.top_k)]

    def _metric_observations(
        self,
        user_id: UUID,
        metric_type: MetricType,
        end_date: date,
        days: int,
    ) -> list[Observation]:
        start_date = end_date - timedelta(days=days - 1)
        rows = self.session.scalars(
            select(ObservationTable)
            .where(
                ObservationTable.user_id == str(user_id),
                ObservationTable.metric_type == metric_type.value,
                ObservationTable.observed_at
                >= datetime.combine(start_date, datetime.min.time(), UTC),
                ObservationTable.observed_at
                <= datetime.combine(end_date, datetime.max.time(), UTC),
            )
            .order_by(ObservationTable.observed_at, ObservationTable.observation_id)
        ).all()
        return [_observation(row) for row in rows]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _observation(row: ObservationTable) -> Observation:
    return Observation(
        observation_id=UUID(row.observation_id),
        user_id=UUID(row.user_id),
        metric_type=MetricType(row.metric_type),
        value_numeric=row.value_numeric,
        value_boolean=row.value_boolean,
        unit=ObservationUnit(row.unit) if row.unit else None,
        observed_at=_as_utc(row.observed_at),
        source_type=SourceType(row.source_type),
        quality_flag=QualityFlag(row.quality_flag),
        confidence=row.confidence,
        metadata=row.metadata_json,
    )
