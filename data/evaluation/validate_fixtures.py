from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean, pstdev

from backend.domain.models import (
    Goal,
    InterventionPlan,
    JournalEntry,
    Observation,
    PlanAction,
    PlanFeedback,
    UserProfile,
)

REQUIRED_FILES = {
    "profile.json",
    "observations.csv",
    "journal_entries.json",
    "goals.json",
    "intervention_history.json",
    "scenario.json",
    "ground_truth.json",
    "expected_findings.json",
    "audit.json",
}
REQUIRED_PLOTS = {"sleep.svg", "activity.svg", "stress_mood.svg", "heart_rate.svg"}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_observations(path: Path) -> list[Observation]:
    observations: list[Observation] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
            observations.append(
                Observation.model_validate(
                    {
                        **row,
                        "value_numeric": row["value_numeric"] or None,
                        "value_boolean": row["value_boolean"] or None,
                        "unit": row["unit"] or None,
                        "confidence": row["confidence"] or None,
                        "metadata": metadata,
                    }
                )
            )
    return observations


def _values_by_metric(observations: list[Observation]) -> dict[str, list[tuple[int, float]]]:
    values: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for observation in observations:
        if observation.value_numeric is None or observation.quality_flag == "missing":
            continue
        metadata = observation.metadata or {}
        day = int(metadata["day_index"])
        values[str(observation.metric_type)].append((day, observation.value_numeric))
    return values


def _mean_days(values: list[tuple[int, float]], start: int, end: int) -> float:
    selected = [value for day, value in values if start <= day <= end]
    if not selected:
        raise ValueError(f"no values in day range {start}-{end}")
    return fmean(selected)


def _feedback_ratios(history: dict[str, object]) -> list[tuple[str, float]]:
    raw_feedback = history["plan_feedback"]
    if not isinstance(raw_feedback, list):
        raise TypeError("plan_feedback must be a list")
    ratios: list[tuple[str, float]] = []
    for item in raw_feedback:
        feedback = PlanFeedback.model_validate(item)
        if feedback.completion_ratio is not None:
            ratios.append((feedback.created_at.isoformat(), feedback.completion_ratio))
    return sorted(ratios)


def _validate_scenario_pattern(
    scenario_id: str,
    observations: list[Observation],
    journals: list[JournalEntry],
    history: dict[str, object],
) -> None:
    values = _values_by_metric(observations)
    steps = values["steps"]
    sleep = values["sleep_duration"]
    stress = values["stress_score"]
    mood = values["mood_score"]
    heart_rate = values["resting_heart_rate"]

    if scenario_id == "irregular_sleep_grad_student":
        starts = [value for _, value in values["sleep_start_time"]]
        if pstdev(starts) < 90:
            raise ValueError("irregular-sleep scenario lacks sleep timing variability")
    elif scenario_id == "sedentary_remote_worker":
        if fmean(value for _, value in steps) >= 4000:
            raise ValueError("sedentary scenario activity is too high")
    elif scenario_id == "high_stress_office_worker":
        if _mean_days(stress, 15, 28) <= _mean_days(stress, 0, 13) + 1.5:
            raise ValueError("high-stress scenario lacks stress increase")
        if _mean_days(mood, 15, 28) >= _mean_days(mood, 0, 13) - 1.0:
            raise ValueError("high-stress scenario lacks mood decline")
        if _mean_days(steps, 15, 28) >= _mean_days(steps, 0, 13) - 1000:
            raise ValueError("high-stress scenario lacks activity decline")
    elif scenario_id == "return_to_activity":
        if _mean_days(steps, 38, 44) <= _mean_days(steps, 0, 6) + 3000:
            raise ValueError("return-to-activity scenario lacks recovery trend")
        ratios = _feedback_ratios(history)
        if ratios[-1][1] <= ratios[0][1] + 0.25:
            raise ValueError("return-to-activity scenario lacks adherence improvement")
    elif scenario_id == "mild_fall_risk_older_adult":
        near_falls = [
            observation
            for observation in observations
            if str(observation.metric_type) == "near_fall_event" and observation.value_boolean
        ]
        falls = [
            observation
            for observation in observations
            if str(observation.metric_type) == "fall_event" and observation.value_boolean
        ]
        if len(near_falls) != 2 or falls:
            raise ValueError("fall-risk scenario event truth does not match catalog")
    elif scenario_id == "structured_missingness_user":
        missing = [
            observation for observation in observations if observation.quality_flag == "missing"
        ]
        reasons = {
            (observation.metadata or {}).get("missingness_reason") for observation in missing
        }
        if reasons != {"simulated_device_nonwear", "simulated_checkin_gap"}:
            raise ValueError("structured-missingness scenario lacks both missingness blocks")
    elif scenario_id == "stable_metrics_subjective_discomfort":
        discomfort = [journal for journal in journals if "drained" in journal.text]
        if len(discomfort) < 10:
            raise ValueError("subjective-discomfort scenario lacks journal signal")
        if max(value for _, value in sleep) - min(value for _, value in sleep) >= 0.5:
            raise ValueError("subjective-discomfort sleep is not stable")
        if max(value for _, value in heart_rate) - min(value for _, value in heart_rate) >= 2:
            raise ValueError("subjective-discomfort heart rate is not stable")
    elif scenario_id == "low_adherence_user":
        ratios = _feedback_ratios(history)
        if ratios[-1][1] >= ratios[0][1] - 0.35:
            raise ValueError("low-adherence scenario lacks adherence decline")
    elif scenario_id == "recovery_after_disruption":
        if _mean_days(sleep, 15, 21) >= _mean_days(sleep, 0, 13) - 0.7:
            raise ValueError("recovery scenario lacks disruption")
        if abs(_mean_days(sleep, 37, 44) - _mean_days(sleep, 0, 13)) >= 0.35:
            raise ValueError("recovery scenario does not return toward baseline")
    elif scenario_id == "balanced_routine_user":
        if max(value for _, value in sleep) - min(value for _, value in sleep) >= 0.4:
            raise ValueError("balanced routine sleep is not stable")
        if max(value for _, value in stress) - min(value for _, value in stress) >= 0.6:
            raise ValueError("balanced routine stress is not stable")


def validate_fixture(path: Path) -> None:
    missing_files = REQUIRED_FILES - {item.name for item in path.iterdir() if item.is_file()}
    if missing_files:
        raise ValueError(f"missing fixture files: {sorted(missing_files)}")
    plots_dir = path / "plots"
    if not plots_dir.is_dir():
        raise ValueError("fixture plots directory is missing")
    missing_plots = REQUIRED_PLOTS - {item.name for item in plots_dir.iterdir() if item.is_file()}
    if missing_plots:
        raise ValueError(f"missing fixture plots: {sorted(missing_plots)}")

    scenario = _load_json(path / "scenario.json")
    scenario_id = str(scenario["id"])
    UserProfile.model_validate(_load_json(path / "profile.json"))
    observations = _load_observations(path / "observations.csv")
    journals = [
        JournalEntry.model_validate(item) for item in _load_json(path / "journal_entries.json")
    ]
    for item in _load_json(path / "goals.json"):
        Goal.model_validate(item)

    history = _load_json(path / "intervention_history.json")
    for item in history["plans"]:
        InterventionPlan.model_validate(item)
    for item in history["actions"]:
        PlanAction.model_validate(item)
    for item in history["plan_feedback"]:
        PlanFeedback.model_validate(item)

    ground_truth = _load_json(path / "ground_truth.json")
    sentences = ground_truth.get("sentences")
    if not isinstance(sentences, list) or not 3 <= len(sentences) <= 5:
        raise ValueError("ground truth must contain 3-5 sentences")
    if (
        ground_truth.get("scenario_id") != scenario_id
        or ground_truth.get("synthetic_only") is not True
    ):
        raise ValueError("ground truth metadata is inconsistent")

    findings = _load_json(path / "expected_findings.json")
    if findings.get("scenario_id") != scenario_id or not findings.get("findings"):
        raise ValueError("expected findings are missing or inconsistent")
    for finding in findings["findings"]:
        if (
            not finding.get("id")
            or not finding.get("description")
            or not finding.get("evidence_metrics")
        ):
            raise ValueError("expected finding is incomplete")

    audit = _load_json(path / "audit.json")
    if audit.get("status") != "pass" or not all(audit.get("checks", {}).values()):
        raise ValueError("fixture audit did not pass")

    for plot_name in REQUIRED_PLOTS:
        content = (plots_dir / plot_name).read_text(encoding="utf-8")
        if "<svg" not in content or "<polyline" not in content:
            raise ValueError(f"plot {plot_name} is not a populated SVG time series")

    _validate_scenario_pattern(scenario_id, observations, journals, history)


def validate_all(root: Path) -> None:
    fixture_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if len(fixture_dirs) != 10:
        raise ValueError("evaluation fixture root must contain exactly 10 persona packages")
    for fixture_dir in fixture_dirs:
        validate_fixture(fixture_dir)
