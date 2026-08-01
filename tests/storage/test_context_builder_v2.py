from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.agents.context_builder import ContextBuilderService, SummaryStatementKind
from backend.domain.models import MetricType
from backend.storage.models import JournalEntryTable, ObservationTable, UserProfileTable
from data.synthetic.generate import generate


def _seed_generated_profiles_and_observations(session: Session, output: Path) -> None:
    profiles = json.loads((output / "profile.json").read_text(encoding="utf-8"))
    for profile in profiles:
        session.add(
            UserProfileTable(
                user_id=profile["user_id"],
                age_band=profile["age_band"],
                preferred_language=profile["preferred_language"],
                timezone=profile["timezone"],
                schedule_constraints=profile["schedule_constraints"],
                health_goals=profile["health_goals"],
                activity_constraints=profile["activity_constraints"],
                coaching_preferences=profile["coaching_preferences"],
                consent_flags=profile["consent_flags"],
            )
        )
    session.flush()

    with (output / "observations.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            session.add(
                ObservationTable(
                    observation_id=row["observation_id"],
                    user_id=row["user_id"],
                    metric_type=row["metric_type"],
                    value_numeric=float(row["value_numeric"]) if row["value_numeric"] else None,
                    value_boolean=None,
                    unit=row["unit"] or None,
                    observed_at=datetime.fromisoformat(row["observed_at"]),
                    source_type=row["source_type"],
                    quality_flag=row["quality_flag"],
                    confidence=float(row["confidence"]) if row["confidence"] else None,
                    metadata_json=json.loads(row["metadata"]) if row["metadata"] else None,
                )
            )
    session.flush()


def test_context_builder_matches_ground_truth_trends_for_all_ten_personas(
    database_session: Session,
    tmp_path: Path,
) -> None:
    output = tmp_path / "synthetic"
    generate(42, 45, output)
    _seed_generated_profiles_and_observations(database_session, output)
    truth = json.loads((output / "ground_truth.json").read_text(encoding="utf-8"))
    dataset_start = datetime(2026, 1, 1, tzinfo=UTC)

    assert len(truth["personas"]) == 10
    for persona in truth["personas"]:
        end_at = dataset_start + timedelta(days=persona["change_point"]["end_day"], hours=23)
        summary = ContextBuilderService(database_session).build(
            UUID(persona["user_id"]),
            end_at=end_at,
        )
        trends = {item.metric_type: item for item in summary.significant_trends}

        assert trends[MetricType.SLEEP_DURATION].direction == "decreased"
        assert trends[MetricType.STRESS_SCORE].direction == "increased"
        assert trends[MetricType.STEPS].direction == "decreased"
        assert len(summary.metrics_7d) >= 6
        assert len(summary.metrics_30d) >= 6
        assert all(item.source_record_ids for item in summary.metrics_7d)
        assert all(item.kind is SummaryStatementKind.FACT for item in summary.facts)
        assert summary.source_record_ids


def test_context_builder_separates_subjective_text_and_marks_missing_data(
    database_session: Session,
) -> None:
    user_id = uuid4()
    database_session.add(
        UserProfileTable(
            user_id=str(user_id),
            age_band="30-44",
            preferred_language="en",
            timezone="UTC",
            schedule_constraints={"weekday_evening_minutes": 10},
            health_goals=["sleep"],
            activity_constraints=None,
            coaching_preferences={"style": "brief"},
            consent_flags={"demo": True},
        )
    )
    database_session.flush()
    database_session.add(
        JournalEntryTable(
            entry_id=str(uuid4()),
            user_id=str(user_id),
            created_at=datetime(2026, 7, 30, 12, tzinfo=UTC),
            text="I felt stressed and my sleep routine was difficult last night.",
            language="en",
            user_tags=["sleep"],
        )
    )
    database_session.flush()

    summary = ContextBuilderService(database_session).build(
        user_id,
        end_at=datetime(2026, 7, 30, 23, tzinfo=UTC),
    )

    assert summary.subjective_descriptions
    assert summary.subjective_descriptions[0].kind is SummaryStatementKind.SUBJECTIVE
    assert "sleep" in summary.journal_themes
    assert not summary.metrics_7d
    assert "sleep_duration:7d" in summary.data_insufficient
    assert "sleep_duration:30d" in summary.data_insufficient
    assert summary.adherence.completion_rate is None
    assert summary.preferences == {"style": "brief"}
    assert summary.constraints["weekday_evening_minutes"] == 10
