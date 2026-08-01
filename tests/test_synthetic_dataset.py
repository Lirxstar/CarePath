import csv
import json
import math
from pathlib import Path
from statistics import fmean

import pytest

from data.synthetic.generate import DOMAINS, generate, validate_generated_dataset

REQUIRED_FILES = {
    "profile.json",
    "observations.csv",
    "journal_entries.json",
    "goals.json",
    "intervention_history.json",
}
EXPECTED_METRICS = {
    "sleep_duration",
    "steps",
    "active_minutes",
    "resting_heart_rate",
    "stress_score",
    "mood_score",
    "activity_confidence",
}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _observation_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _correlation(xs: list[float], ys: list[float]) -> float:
    x_mean = fmean(xs)
    y_mean = fmean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    x_energy = sum((x - x_mean) ** 2 for x in xs)
    y_energy = sum((y - y_mean) ** 2 for y in ys)
    return numerator / math.sqrt(x_energy * y_energy)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("synthetic")
    generate(42, 45, output)
    return output


def test_output_contract_and_canonical_validation(dataset: Path) -> None:
    assert {path.name for path in dataset.iterdir()} >= REQUIRED_FILES

    profiles = _load_json(dataset / "profile.json")
    truth = _load_json(dataset / "ground_truth.json")
    rows = _observation_rows(dataset / "observations.csv")

    assert len(profiles) == 10
    assert truth["days"] == 45
    assert truth["seed"] == 42
    assert len(truth["personas"]) == 10
    assert set(truth["design"]["domains"]) == set(DOMAINS)
    assert {row["metric_type"] for row in rows} == EXPECTED_METRICS
    assert {profile["preferred_language"] for profile in profiles} == {"en", "zh", "ja"}
    assert len({profile["timezone"] for profile in profiles}) == 3
    assert all(set(profile["health_goals"]) == set(DOMAINS) for profile in profiles)

    validate_generated_dataset(dataset)


def test_same_seed_is_exact_and_different_seed_changes_output(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"

    generate(7, 30, first)
    generate(7, 30, second)
    generate(8, 30, third)

    for name in REQUIRED_FILES | {"ground_truth.json"}:
        assert (first / name).read_bytes() == (second / name).read_bytes()

    assert (first / "observations.csv").read_bytes() != (third / "observations.csv").read_bytes()
    assert (first / "profile.json").read_bytes() != (third / "profile.json").read_bytes()


def test_missingness_is_structured_and_matches_ground_truth(dataset: Path) -> None:
    rows = _observation_rows(dataset / "observations.csv")
    truth = _load_json(dataset / "ground_truth.json")
    missing_days: dict[str, set[int]] = {}

    for row in rows:
        if row["quality_flag"] != "missing":
            continue
        metadata = json.loads(row["metadata"])
        missingness_id = metadata["missingness_id"]
        assert metadata["missingness_reason"] in {
            "simulated_device_nonwear",
            "simulated_checkin_gap",
        }
        assert row["value_numeric"] == ""
        missing_days.setdefault(missingness_id, set()).add(int(metadata["day_index"]))

    truth_ids = {
        event["missingness_id"] for persona in truth["personas"] for event in persona["missingness"]
    }
    assert set(missing_days) == truth_ids
    assert all(len(days) >= 2 for days in missing_days.values())
    for days in missing_days.values():
        assert days == set(range(min(days), max(days) + 1))


def test_change_points_have_expected_direction_and_adherence_decline(dataset: Path) -> None:
    rows = _observation_rows(dataset / "observations.csv")
    truth = _load_json(dataset / "ground_truth.json")
    values = {
        (row["user_id"], row["metric_type"], int(json.loads(row["metadata"])["day_index"])): float(
            row["value_numeric"]
        )
        for row in rows
        if row["quality_flag"] == "valid"
    }

    for persona in truth["personas"]:
        user_id = persona["user_id"]
        event = persona["change_point"]
        sleep_deltas = []
        stress_deltas = []
        step_deltas = []

        for day in range(event["start_day"], event["end_day"] + 1):
            previous_day = day - 7
            sleep_key = (user_id, "sleep_duration", day)
            previous_sleep_key = (user_id, "sleep_duration", previous_day)
            if sleep_key in values and previous_sleep_key in values:
                sleep_deltas.append(values[sleep_key] - values[previous_sleep_key])

            stress_key = (user_id, "stress_score", day)
            previous_stress_key = (user_id, "stress_score", previous_day)
            if stress_key in values and previous_stress_key in values:
                stress_deltas.append(values[stress_key] - values[previous_stress_key])

            steps_key = (user_id, "steps", day)
            previous_steps_key = (user_id, "steps", previous_day)
            if steps_key in values and previous_steps_key in values:
                step_deltas.append(values[steps_key] - values[previous_steps_key])

        assert fmean(sleep_deltas) < -0.6
        assert fmean(stress_deltas) > 1.2
        assert fmean(step_deltas) < -1000

    history = _load_json(dataset / "intervention_history.json")
    event_feedback = [
        item
        for item in history["plan_feedback"]
        if item["reason_text"] == "Synthetic adherence decline during the injected stress event."
    ]
    assert len(event_feedback) >= 40
    assert all(item["completion_ratio"] < 0.85 for item in event_feedback)


def test_contradictions_are_explicit_and_linked(dataset: Path) -> None:
    rows = _observation_rows(dataset / "observations.csv")
    truth = _load_json(dataset / "ground_truth.json")
    journals = _load_json(dataset / "journal_entries.json")
    rows_by_id = {row["observation_id"]: row for row in rows}
    journals_by_id = {entry["entry_id"]: entry for entry in journals}

    for persona in truth["personas"]:
        contradiction = persona["contradictions"][0]
        journal = journals_by_id[contradiction["journal_entry_id"]]
        linked_rows = [rows_by_id[item] for item in contradiction["observation_ids"]]

        assert "synthetic_contradiction" in journal["user_tags"]
        assert contradiction["contradiction_id"] in journal["user_tags"]
        by_metric = {row["metric_type"]: row for row in linked_rows}
        assert float(by_metric["sleep_duration"]["value_numeric"]) >= 7.8
        assert float(by_metric["steps"]["value_numeric"]) >= 8200
        for row in linked_rows:
            assert (
                json.loads(row["metadata"])["contradiction_id"] == contradiction["contradiction_id"]
            )


def test_designed_metric_correlations_are_present(dataset: Path) -> None:
    rows = _observation_rows(dataset / "observations.csv")
    values: dict[tuple[str, int], dict[str, float]] = {}

    for row in rows:
        if row["quality_flag"] != "valid":
            continue
        metadata = json.loads(row["metadata"])
        key = (row["user_id"], int(metadata["day_index"]))
        values.setdefault(key, {})[row["metric_type"]] = float(row["value_numeric"])

    def paired(metric_x: str, metric_y: str) -> tuple[list[float], list[float]]:
        pairs = [
            (metrics[metric_x], metrics[metric_y])
            for metrics in values.values()
            if metric_x in metrics and metric_y in metrics
        ]
        return [pair[0] for pair in pairs], [pair[1] for pair in pairs]

    steps, active = paired("steps", "active_minutes")
    stress, heart_rate = paired("stress_score", "resting_heart_rate")
    stress_for_mood, mood = paired("stress_score", "mood_score")

    assert _correlation(steps, active) > 0.9
    assert _correlation(stress, heart_rate) > 0.3
    assert _correlation(stress_for_mood, mood) < -0.6


@pytest.mark.parametrize("days", [29, 61])
def test_duration_validation(tmp_path: Path, days: int) -> None:
    with pytest.raises(ValueError, match="between 30 and 60"):
        generate(42, days, tmp_path)
