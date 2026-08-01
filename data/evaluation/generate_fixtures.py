from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from backend.domain.models import (
    Goal,
    InterventionPlan,
    JournalEntry,
    Observation,
    PlanAction,
    PlanFeedback,
    UserProfile,
)

DOMAINS = ["sleep", "physical_activity", "stress_mood", "falls_activity_safety"]
OBSERVATION_FIELDS = [
    "observation_id",
    "user_id",
    "metric_type",
    "value_numeric",
    "value_boolean",
    "unit",
    "observed_at",
    "source_type",
    "quality_flag",
    "confidence",
    "metadata",
]
METRIC_UNITS: dict[str, str | None] = {
    "sleep_duration": "hours",
    "sleep_start_time": "minutes_since_midnight",
    "sleep_end_time": "minutes_since_midnight",
    "steps": "steps",
    "active_minutes": "minutes",
    "resting_heart_rate": "bpm",
    "stress_score": "score_1_10",
    "mood_score": "score_1_10",
    "activity_confidence": "score_1_10",
    "fall_event": None,
    "near_fall_event": None,
}
PLOT_SPECS = {
    "sleep.svg": ["sleep_duration"],
    "activity.svg": ["steps", "active_minutes"],
    "stress_mood.svg": ["stress_score", "mood_score"],
    "heart_rate.svg": ["resting_heart_rate"],
}


def _uid(seed: int, scenario_id: str, name: str) -> str:
    namespace = UUID("00000000-0000-0000-0000-000000000000")
    return str(uuid5(namespace, f"carepath-eval:{seed}:{scenario_id}:{name}"))


def _dump(model: Any) -> dict[str, object]:
    return dict(model.model_dump(mode="json"))


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(f"{text}\n", encoding="utf-8")


def load_catalog() -> dict[str, object]:
    path = Path(__file__).with_name("scenario_catalog.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _observation(
    *,
    seed: int,
    scenario_id: str,
    day: int,
    metric: str,
    user_id: str,
    observed_at: datetime,
    value: float | bool | None,
    source_type: str,
    missing: bool = False,
    metadata: dict[str, object] | None = None,
) -> Observation:
    numeric_value: float | None = None
    boolean_value: bool | None = None
    if not missing:
        if isinstance(value, bool):
            boolean_value = value
        elif value is not None:
            numeric_value = float(value)
    return Observation(
        observation_id=_uid(seed, scenario_id, f"obs-{day}-{metric}"),
        user_id=user_id,
        metric_type=metric,
        value_numeric=numeric_value,
        value_boolean=boolean_value,
        unit=METRIC_UNITS[metric],
        observed_at=observed_at,
        source_type=source_type,
        quality_flag="missing" if missing else "valid",
        confidence=0.0 if missing else 0.95,
        metadata=metadata or {},
    )


def _scenario_values(
    scenario_id: str,
    day: int,
    days: int,
    rng: random.Random,
) -> dict[str, float]:
    weekly = math.sin(2 * math.pi * day / 7)
    progress = day / max(1, days - 1)
    sleep = 7.15 + 0.12 * weekly + rng.uniform(-0.12, 0.12)
    sleep_start = 1380 + 10 * weekly + rng.uniform(-8, 8)
    sleep_end = 420 + 10 * weekly + rng.uniform(-8, 8)
    steps = 7200 + 350 * weekly + rng.randint(-250, 250)
    stress = 4.2 - 0.15 * weekly + rng.uniform(-0.22, 0.22)
    mood = 7.1 + 0.12 * weekly + rng.uniform(-0.22, 0.22)
    rhr = 61 + 0.6 * stress + rng.uniform(-0.8, 0.8)
    confidence = 8.1 + rng.uniform(-0.18, 0.18)

    if scenario_id == "irregular_sleep_grad_student":
        shift = ((day * 97) % 310) - 155
        weekend = 110 if (datetime(2026, 1, 1) + timedelta(days=day)).weekday() >= 5 else 0
        sleep_start = (1320 + shift + weekend) % 1440
        sleep_end = (390 + shift + weekend) % 1440
        sleep = 6.9 + 0.35 * math.sin(2 * math.pi * day / 5) + rng.uniform(-0.25, 0.25)
    elif scenario_id == "sedentary_remote_worker":
        steps = 2600 + 180 * weekly + rng.randint(-180, 180)
        confidence = 6.6 + rng.uniform(-0.2, 0.2)
    elif scenario_id == "high_stress_office_worker":
        if 15 <= day <= 28:
            stress += 2.8
            mood -= 1.7
            steps -= 1900
            rhr += 4.0
    elif scenario_id == "return_to_activity":
        steps = 2800 + 5200 * progress + rng.randint(-220, 220)
        confidence = 5.8 + 2.2 * progress + rng.uniform(-0.15, 0.15)
    elif scenario_id == "mild_fall_risk_older_adult":
        steps = 4700 + 220 * weekly + rng.randint(-180, 180)
        confidence = 5.7 + rng.uniform(-0.2, 0.2)
        if day in {13, 31}:
            confidence -= 1.2
    elif scenario_id == "stable_metrics_subjective_discomfort":
        sleep = 7.2 + rng.uniform(-0.08, 0.08)
        steps = 6900 + rng.randint(-180, 180)
        stress = 4.1 + rng.uniform(-0.12, 0.12)
        mood = 6.9 + rng.uniform(-0.12, 0.12)
        rhr = 63 + rng.uniform(-0.6, 0.6)
    elif scenario_id == "low_adherence_user":
        steps = 6500 + 220 * weekly + rng.randint(-220, 220)
    elif scenario_id == "recovery_after_disruption":
        if 15 <= day <= 21:
            sleep -= 1.25
            stress += 2.4
            steps -= 2100
        elif 22 <= day <= 30:
            recovery = (day - 21) / 9
            sleep -= 1.25 * (1 - recovery)
            stress += 2.4 * (1 - recovery)
            steps -= 2100 * (1 - recovery)
    elif scenario_id == "balanced_routine_user":
        sleep = 7.35 + rng.uniform(-0.09, 0.09)
        steps = 7600 + rng.randint(-220, 220)
        stress = 3.8 + rng.uniform(-0.14, 0.14)
        mood = 7.5 + rng.uniform(-0.14, 0.14)
        rhr = 62 + rng.uniform(-0.6, 0.6)
        confidence = 8.5 + rng.uniform(-0.12, 0.12)

    stress = min(10.0, max(1.0, stress))
    mood = min(10.0, max(1.0, mood))
    sleep = min(10.5, max(4.0, sleep))
    steps = max(500.0, float(round(steps)))
    active_minutes = max(4.0, steps / 120 + rng.uniform(-2.5, 2.5))
    if scenario_id == "sedentary_remote_worker":
        active_minutes = max(5.0, steps / 155 + rng.uniform(-1.5, 1.5))
    return {
        "sleep_duration": round(sleep, 2),
        "sleep_start_time": round(sleep_start % 1440, 1),
        "sleep_end_time": round(sleep_end % 1440, 1),
        "steps": steps,
        "active_minutes": round(active_minutes, 2),
        "resting_heart_rate": round(max(45.0, rhr), 2),
        "stress_score": round(stress, 2),
        "mood_score": round(mood, 2),
        "activity_confidence": round(min(10.0, max(1.0, confidence)), 2),
    }


def _journal_text(scenario_id: str, day: int) -> str:
    if scenario_id == "stable_metrics_subjective_discomfort" and day % 3 == 1:
        return (
            "My numbers look normal, but I still feel unusually drained and not quite myself today."
        )
    if scenario_id == "low_adherence_user" and day % 7 in {4, 5}:
        return "My schedule got in the way again, so I did not manage the routine I had planned."
    if scenario_id == "high_stress_office_worker" and 15 <= day <= 28:
        return "Work pressure felt heavy today and it was harder to keep my usual routine."
    if scenario_id == "recovery_after_disruption" and 15 <= day <= 21:
        return (
            "This week feels disrupted; sleep, stress, and activity are all harder to keep steady."
        )
    if scenario_id == "return_to_activity" and day >= 21:
        return (
            "I am getting back into regular movement gradually and "
            "the routine feels more manageable."
        )
    return "Routine synthetic check-in; no major subjective change to report today."


def _feedback_ratio(scenario_id: str, day: int, days: int) -> float:
    progress = day / max(1, days - 1)
    if scenario_id == "low_adherence_user":
        return max(0.25, 0.9 - 0.62 * progress)
    if scenario_id == "return_to_activity":
        return min(0.96, 0.48 + 0.47 * progress)
    if scenario_id == "recovery_after_disruption" and 15 <= day <= 21:
        return 0.52
    return 0.88


def _write_observations(path: Path, observations: list[Observation]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OBSERVATION_FIELDS)
        writer.writeheader()
        for observation in observations:
            row = _dump(observation)
            row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)
            for key in ("value_numeric", "value_boolean", "unit", "confidence"):
                if row[key] is None:
                    row[key] = ""
            writer.writerow(row)


def _svg_plot(path: Path, title: str, series: dict[str, list[float | None]]) -> None:
    width, height = 760, 300
    left, right, top, bottom = 55, 20, 35, 35
    all_values = [value for values in series.values() for value in values if value is not None]
    if not all_values:
        all_values = [0.0, 1.0]
    low, high = min(all_values), max(all_values)
    if math.isclose(low, high):
        low -= 1
        high += 1
    count = max(len(values) for values in series.values())

    def point(index: int, value: float) -> tuple[float, float]:
        x = left + (width - left - right) * index / max(1, count - 1)
        y = top + (height - top - bottom) * (high - value) / (high - low)
        return x, y

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="22" font-family="sans-serif" font-size="16">{title}</text>',
        (
            f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" '
            f'y2="{height - bottom}" stroke="black"/>'
        ),
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="black"/>',
    ]
    dash_patterns = ["", "6 4", "2 3"]
    for series_index, (name, values) in enumerate(series.items()):
        segments: list[str] = []
        current: list[str] = []
        for index, value in enumerate(values):
            if value is None:
                if current:
                    segments.append(" ".join(current))
                    current = []
                continue
            x, y = point(index, value)
            current.append(f"{x:.1f},{y:.1f}")
        if current:
            segments.append(" ".join(current))
        dash = dash_patterns[series_index % len(dash_patterns)]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        for segment in segments:
            parts.append(
                f'<polyline points="{segment}" fill="none" stroke="black" '
                f'stroke-width="2"{dash_attr}/>'
            )
        parts.append(
            f'<text x="{left + 165 * series_index}" y="{height - 8}" '
            f'font-family="sans-serif" font-size="12">{name}</text>'
        )
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def _audit(
    scenario: dict[str, object],
    observations: list[Observation],
    journals: list[dict[str, object]],
    days: int,
) -> dict[str, object]:
    unit_errors: list[str] = []
    date_errors: list[str] = []
    range_errors: list[str] = []
    missing_by_metric: dict[str, int] = defaultdict(int)
    counts_by_metric: dict[str, int] = defaultdict(int)
    values_by_metric: dict[str, list[float]] = defaultdict(list)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=days, hours=23)

    for observation in observations:
        metric = str(observation.metric_type)
        counts_by_metric[metric] += 1
        if observation.unit != METRIC_UNITS[metric]:
            unit_errors.append(str(observation.observation_id))
        if not start <= observation.observed_at <= end:
            date_errors.append(str(observation.observation_id))
        if str(observation.quality_flag) == "missing":
            missing_by_metric[metric] += 1
        elif observation.value_numeric is not None:
            values_by_metric[metric].append(observation.value_numeric)

    missing_rates = {
        metric: round(missing_by_metric[metric] / count, 4)
        for metric, count in sorted(counts_by_metric.items())
    }
    expected_missing = scenario["id"] == "structured_missingness_user"
    has_missing = any(rate > 0 for rate in missing_rates.values())
    if expected_missing != has_missing:
        range_errors.append("missingness pattern does not match scenario definition")

    if len(journals) < days - 5:
        range_errors.append("too many journal entries are absent")

    return {
        "status": "pass" if not (unit_errors or date_errors or range_errors) else "fail",
        "checks": {
            "schema_validated": True,
            "units_valid": not unit_errors,
            "dates_valid": not date_errors,
            "ranges_valid": not range_errors,
            "missingness_matches_scenario": expected_missing == has_missing,
        },
        "missing_rates": missing_rates,
        "metric_ranges": {
            metric: {"min": round(min(values), 3), "max": round(max(values), 3)}
            for metric, values in sorted(values_by_metric.items())
            if values
        },
        "errors": unit_errors + date_errors + range_errors,
    }


def generate_scenario(scenario: dict[str, object], seed: int, days: int, output: Path) -> None:
    scenario_id = str(scenario["id"])
    rng = random.Random(f"{seed}:{scenario_id}")
    output.mkdir(parents=True, exist_ok=True)
    plots_dir = output / "plots"
    plots_dir.mkdir(exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    user_id = _uid(seed, scenario_id, "user")

    profile = _dump(
        UserProfile(
            user_id=user_id,
            age_band=scenario["age_band"],
            preferred_language=scenario["language"],
            timezone=scenario["timezone"],
            schedule_constraints={"scenario_id": scenario_id},
            health_goals=DOMAINS,
            activity_constraints=["synthetic evaluation fixture"],
            coaching_preferences={"fixture": True},
            consent_flags={"synthetic_data": True, "evaluation_use": True},
        )
    )

    goals: list[dict[str, object]] = []
    goal_ids: dict[str, str] = {}
    for domain in DOMAINS:
        goal_id = _uid(seed, scenario_id, f"goal-{domain}")
        goal_ids[domain] = goal_id
        goals.append(
            _dump(
                Goal(
                    goal_id=goal_id,
                    user_id=user_id,
                    domain=domain,
                    description=f"Maintain a sustainable {domain.replace('_', ' ')} routine",
                    status="active",
                    created_at=start,
                    target_date=(start + timedelta(days=days - 1)).date(),
                )
            )
        )

    plan_id = _uid(seed, scenario_id, "plan")
    plan = _dump(
        InterventionPlan(
            plan_id=plan_id,
            user_id=user_id,
            goal_id=goal_ids["sleep"],
            version=1,
            start_date=start.date(),
            end_date=(start + timedelta(days=days - 1)).date(),
            status="active",
            generation_interaction_id=_uid(seed, scenario_id, "interaction"),
        )
    )
    actions: list[dict[str, object]] = []
    action_ids: list[str] = []
    for domain in DOMAINS:
        action_id = _uid(seed, scenario_id, f"action-{domain}")
        action_ids.append(action_id)
        actions.append(
            _dump(
                PlanAction(
                    action_id=action_id,
                    plan_id=plan_id,
                    domain=domain,
                    description=f"Follow the fixture {domain.replace('_', ' ')} routine",
                    frequency="daily",
                    difficulty="medium",
                    rationale="Synthetic evaluation action for deterministic adherence testing.",
                    status="accepted",
                )
            )
        )

    observations: list[Observation] = []
    journals: list[dict[str, object]] = []
    feedback: list[dict[str, object]] = []
    series: dict[str, list[float | None]] = defaultdict(list)

    for day in range(days):
        observed_at = start + timedelta(days=day, hours=8)
        values = _scenario_values(scenario_id, day, days, rng)
        wearable_missing = scenario_id == "structured_missingness_user" and 18 <= day <= 22
        self_report_missing = scenario_id == "structured_missingness_user" and 28 <= day <= 31

        for metric in (
            "sleep_duration",
            "sleep_start_time",
            "sleep_end_time",
            "steps",
            "active_minutes",
            "resting_heart_rate",
            "activity_confidence",
        ):
            metadata: dict[str, object] = {"day_index": day, "scenario_id": scenario_id}
            if wearable_missing:
                metadata.update(
                    {
                        "missingness_id": _uid(seed, scenario_id, "wearable-nonwear"),
                        "missingness_reason": "simulated_device_nonwear",
                    }
                )
            observation = _observation(
                seed=seed,
                scenario_id=scenario_id,
                day=day,
                metric=metric,
                user_id=user_id,
                observed_at=observed_at,
                value=values[metric],
                source_type="synthetic_wearable",
                missing=wearable_missing,
                metadata=metadata,
            )
            observations.append(observation)
            series[metric].append(None if wearable_missing else values[metric])

        for metric in ("stress_score", "mood_score"):
            metadata = {"day_index": day, "scenario_id": scenario_id}
            if self_report_missing:
                metadata.update(
                    {
                        "missingness_id": _uid(seed, scenario_id, "self-report-gap"),
                        "missingness_reason": "simulated_checkin_gap",
                    }
                )
            observation = _observation(
                seed=seed,
                scenario_id=scenario_id,
                day=day,
                metric=metric,
                user_id=user_id,
                observed_at=observed_at + timedelta(hours=12),
                value=values[metric],
                source_type="self_report",
                missing=self_report_missing,
                metadata=metadata,
            )
            observations.append(observation)
            series[metric].append(None if self_report_missing else values[metric])

        if scenario_id == "mild_fall_risk_older_adult":
            near_fall = day in {13, 31}
            for metric, value in (("near_fall_event", near_fall), ("fall_event", False)):
                observations.append(
                    _observation(
                        seed=seed,
                        scenario_id=scenario_id,
                        day=day,
                        metric=metric,
                        user_id=user_id,
                        observed_at=observed_at + timedelta(hours=6),
                        value=value,
                        source_type="self_report",
                        metadata={"day_index": day, "scenario_id": scenario_id},
                    )
                )

        if not self_report_missing:
            journals.append(
                _dump(
                    JournalEntry(
                        entry_id=_uid(seed, scenario_id, f"journal-{day}"),
                        user_id=user_id,
                        created_at=observed_at + timedelta(hours=13),
                        text=_journal_text(scenario_id, day),
                        language=scenario["language"],
                        user_tags=["synthetic", "evaluation_fixture", scenario_id],
                    )
                )
            )

        if day % 7 == 6 or day == days - 1:
            ratio = round(_feedback_ratio(scenario_id, day, days), 2)
            response = "completed" if ratio >= 0.85 else "partially_completed"
            if ratio < 0.4:
                response = "not_completed"
            for action_id in action_ids:
                feedback.append(
                    _dump(
                        PlanFeedback(
                            feedback_id=_uid(seed, scenario_id, f"feedback-{day}-{action_id}"),
                            action_id=action_id,
                            user_id=user_id,
                            response=response,
                            completion_ratio=ratio,
                            reason_text="Deterministic evaluation fixture adherence check-in.",
                            created_at=observed_at + timedelta(hours=13),
                        )
                    )
                )

    audit = _audit(scenario, observations, journals, days)
    if audit["status"] != "pass":
        raise ValueError(f"fixture audit failed for {scenario_id}: {audit['errors']}")

    _write_json(output / "profile.json", profile)
    _write_observations(output / "observations.csv", observations)
    _write_json(output / "journal_entries.json", journals)
    _write_json(output / "goals.json", goals)
    _write_json(
        output / "intervention_history.json",
        {"plans": [plan], "actions": actions, "plan_feedback": feedback},
    )
    _write_json(
        output / "scenario.json",
        {
            "id": scenario_id,
            "title": scenario["title"],
            "seed": seed,
            "days": days,
            "age_band": scenario["age_band"],
            "language": scenario["language"],
            "timezone": scenario["timezone"],
        },
    )
    _write_json(
        output / "ground_truth.json",
        {
            "scenario_id": scenario_id,
            "sentences": scenario["ground_truth_sentences"],
            "synthetic_only": True,
        },
    )
    _write_json(
        output / "expected_findings.json",
        {"scenario_id": scenario_id, "findings": scenario["expected_findings"]},
    )
    _write_json(output / "audit.json", audit)

    for filename, metrics in PLOT_SPECS.items():
        _svg_plot(
            plots_dir / filename,
            f"{scenario['title']} - {filename.removesuffix('.svg').replace('_', ' ')}",
            {metric: series[metric] for metric in metrics},
        )


def generate_all(output: Path, seed: int | None = None, days: int | None = None) -> None:
    catalog = load_catalog()
    resolved_seed = int(catalog["seed"] if seed is None else seed)
    resolved_days = int(catalog["days"] if days is None else days)
    if not 30 <= resolved_days <= 60:
        raise ValueError("days must be between 30 and 60")
    scenarios = catalog["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != 10:
        raise ValueError("scenario catalog must contain exactly 10 scenarios")
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise TypeError("each scenario must be an object")
        generate_scenario(scenario, resolved_seed, resolved_days, output / str(scenario["id"]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate audited CarePath evaluation persona packs."
    )
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/generated"))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()
    generate_all(args.output, seed=args.seed, days=args.days)


if __name__ == "__main__":
    main()
