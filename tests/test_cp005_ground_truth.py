import csv
import json
from datetime import date, timedelta
from pathlib import Path

from backend.domain.models import MetricType, Observation
from backend.timeseries.analysis import compare_periods, summarise_missingness
from data.synthetic.generate import generate


def _load_observations(path: Path) -> list[Observation]:
    records: list[Observation] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            records.append(
                Observation.model_validate(
                    {
                        **row,
                        "value_numeric": row["value_numeric"] or None,
                        "value_boolean": row["value_boolean"] or None,
                        "unit": row["unit"] or None,
                        "confidence": row["confidence"] or None,
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    }
                )
            )
    return records


def test_cp003_ground_truth_change_windows_are_detected(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    generate(42, 45, output)

    truth = json.loads((output / "ground_truth.json").read_text(encoding="utf-8"))
    records = _load_observations(output / "observations.csv")
    assert len(truth["personas"]) == 10

    dataset_start = date(2026, 1, 1)
    for persona in truth["personas"]:
        user_records = [item for item in records if str(item.user_id) == persona["user_id"]]
        end_date = dataset_start + timedelta(days=persona["change_point"]["end_day"])

        sleep = compare_periods(
            user_records,
            end_date,
            window_days=7,
            metric=MetricType.SLEEP_DURATION,
        )
        stress = compare_periods(
            user_records,
            end_date,
            window_days=7,
            metric=MetricType.STRESS_SCORE,
        )
        steps = compare_periods(
            user_records,
            end_date,
            window_days=7,
            metric=MetricType.STEPS,
        )

        assert sleep.absolute_change is not None and sleep.absolute_change < 0
        assert stress.absolute_change is not None and stress.absolute_change > 0
        assert steps.absolute_change is not None and steps.absolute_change < 0
        assert sleep.source_observation_ids
        assert stress.source_observation_ids
        assert steps.source_observation_ids


def test_cp003_missingness_and_contradictions_are_visible_to_tools(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    generate(42, 45, output)

    truth = json.loads((output / "ground_truth.json").read_text(encoding="utf-8"))
    records = _load_observations(output / "observations.csv")
    dataset_start = date(2026, 1, 1)
    dataset_end = dataset_start + timedelta(days=44)

    for persona in truth["personas"]:
        user_records = [item for item in records if str(item.user_id) == persona["user_id"]]
        result = summarise_missingness(
            user_records,
            start_date=dataset_start,
            end_date=dataset_end,
            metric=MetricType.STEPS,
        )

        assert result.expected_count == 45
        assert result.explicit_missing_observations >= 2
        assert result.conflicting_count >= 1
        expected_ids = set(persona["contradictions"][0]["observation_ids"])
        source_ids = {str(item) for item in result.source_observation_ids}
        assert expected_ids.intersection(source_ids)
