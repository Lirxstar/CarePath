"""Generate reproducible synthetic longitudinal CarePath datasets.

Usage:
    python -m data.synthetic.generate --seed 42 --days 45 --output data/generated
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass
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

DOMAINS = [
    "sleep",
    "physical_activity",
    "stress_mood",
    "falls_activity_safety",
]
METRIC_UNITS = {
    "sleep_duration": "hours",
    "steps": "steps",
    "active_minutes": "minutes",
    "resting_heart_rate": "bpm",
    "stress_score": "score_1_10",
    "mood_score": "score_1_10",
    "activity_confidence": "score_1_10",
}
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


@dataclass(frozen=True)
class PersonaSpec:
    age_band: str
    language: str
    timezone: str
    sleep: float
    steps: int
    stress: float
    resting_heart_rate: float
    activity_confidence: float
    weekend_step_delta: int
    step_trend_per_day: float
    sleep_trend_total: float
    adherence: float


def _uid(seed: int, name: str) -> str:
    namespace = UUID("00000000-0000-0000-0000-000000000000")
    return str(uuid5(namespace, f"carepath:{seed}:{name}"))


def _spec(index: int) -> PersonaSpec:
    return PersonaSpec(
        age_band=["18-29", "30-44", "45-64", "65+"][index % 4],
        language=["en", "zh", "ja"][index % 3],
        timezone=["Asia/Tokyo", "Europe/Rome", "America/New_York"][index % 3],
        sleep=6.5 + 0.14 * (index % 6),
        steps=5200 + 430 * index,
        stress=3.8 + 0.38 * (index % 5),
        resting_heart_rate=57.0 + 2.2 * (index % 5),
        activity_confidence=8.5 - 0.55 * (index % 4),
        weekend_step_delta=900 if index % 2 == 0 else -500,
        step_trend_per_day=(index - 4.5) * 7.0,
        sleep_trend_total=(index - 4.5) * 0.04,
        adherence=0.92 - 0.035 * (index % 5),
    )


def _dump(model: Any) -> dict[str, object]:
    return dict(model.model_dump(mode="json"))


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    path.write_text(f"{text}\n", encoding="utf-8")


def _journal_text(language: str, state: str) -> str:
    texts = {
        "en": {
            "routine": "Routine day; energy and habits felt broadly stable.",
            "stress": "Workload felt heavier and my routine was harder to maintain.",
            "contradiction": "I barely slept last night and hardly moved today.",
        },
        "zh": {
            "routine": "今天整体规律,精力和日常习惯基本稳定。",
            "stress": "今天压力更大,维持日常习惯比平时困难。",
            "contradiction": "我昨晚几乎没睡,今天也几乎没有活动。",
        },
        "ja": {
            "routine": "今日は概ね規則的で、体調と習慣は安定していた。",
            "stress": "今日は負担が重く、普段の習慣を保つのが難しかった。",
            "contradiction": "昨夜はほとんど眠れず、今日はほとんど動かなかった。",
        },
    }
    return texts[language][state]


def _observation(
    seed: int,
    persona_index: int,
    day_index: int,
    metric_type: str,
    user_id: str,
    observed_at: datetime,
    value: float | None,
    *,
    source_type: str,
    missing: bool,
    metadata: dict[str, object],
) -> Observation:
    return Observation(
        observation_id=_uid(
            seed,
            f"obs-{persona_index}-{day_index}-{metric_type}",
        ),
        user_id=user_id,
        metric_type=metric_type,
        value_numeric=None if missing else value,
        unit=METRIC_UNITS[metric_type],
        observed_at=observed_at,
        source_type=source_type,
        quality_flag="missing" if missing else "valid",
        confidence=0.0 if missing else 0.95,
        metadata=metadata,
    )


def _csv_row(model: Observation) -> dict[str, object]:
    row = _dump(model)
    metadata = row["metadata"]
    row["metadata"] = (
        json.dumps(metadata, sort_keys=True, ensure_ascii=False) if metadata is not None else ""
    )
    for key in ("value_numeric", "value_boolean", "unit", "confidence"):
        if row[key] is None:
            row[key] = ""
    return row


def _parse_csv_row(row: dict[str, str]) -> dict[str, object]:
    payload: dict[str, object] = dict(row)
    payload["value_numeric"] = float(row["value_numeric"]) if row["value_numeric"] else None
    payload["value_boolean"] = None
    payload["unit"] = row["unit"] or None
    payload["confidence"] = float(row["confidence"]) if row["confidence"] else None
    payload["metadata"] = json.loads(row["metadata"]) if row["metadata"] else None
    return payload


def validate_generated_dataset(output: Path) -> None:
    """Validate all generated records against the CP-002 canonical models."""
    profiles = json.loads((output / "profile.json").read_text(encoding="utf-8"))
    journals = json.loads((output / "journal_entries.json").read_text(encoding="utf-8"))
    goals = json.loads((output / "goals.json").read_text(encoding="utf-8"))
    history = json.loads((output / "intervention_history.json").read_text(encoding="utf-8"))

    for record in profiles:
        UserProfile.model_validate(record)
    for record in journals:
        JournalEntry.model_validate(record)
    for record in goals:
        Goal.model_validate(record)
    for record in history["plans"]:
        InterventionPlan.model_validate(record)
    for record in history["actions"]:
        PlanAction.model_validate(record)
    for record in history["plan_feedback"]:
        PlanFeedback.model_validate(record)

    observation_path = output / "observations.csv"
    with observation_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            Observation.model_validate(_parse_csv_row(row))


def _daily_values(
    rng: random.Random,
    spec: PersonaSpec,
    day_index: int,
    days: int,
    *,
    weekend: bool,
    change_window: bool,
    contradiction: bool,
) -> dict[str, float]:
    progress = day_index / max(1, days - 1)
    weekly_wave = math.sin(2 * math.pi * day_index / 7)

    sleep = (
        spec.sleep
        + spec.sleep_trend_total * progress
        + 0.16 * weekly_wave
        + rng.uniform(-0.22, 0.22)
    )
    stress = spec.stress - 0.12 * weekly_wave + rng.uniform(-0.35, 0.35)
    steps = spec.steps + spec.step_trend_per_day * day_index + rng.randint(-450, 450)
    if weekend:
        steps += spec.weekend_step_delta
    if change_window:
        sleep -= 1.15
        stress += 2.0
        steps -= 1800
    if contradiction:
        sleep = max(sleep, 7.8)
        steps = max(steps, 8200)

    sleep = min(10.5, max(4.0, sleep))
    stress = min(10.0, max(1.0, stress))
    steps = max(800.0, float(round(steps)))
    active_minutes = max(5.0, steps / 115 + rng.uniform(-4.0, 4.0))
    resting_heart_rate = (
        spec.resting_heart_rate
        + 0.9 * (stress - 5.0)
        - 0.45 * (sleep - 7.0)
        + rng.uniform(-1.2, 1.2)
    )
    mood = 8.2 - 0.62 * stress + 0.3 * (sleep - 7.0)
    mood += rng.uniform(-0.3, 0.3)
    activity_confidence = spec.activity_confidence + steps / 10000
    activity_confidence -= 0.22 * stress
    activity_confidence += rng.uniform(-0.25, 0.25)

    return {
        "sleep_duration": round(sleep, 2),
        "steps": steps,
        "active_minutes": round(active_minutes, 2),
        "resting_heart_rate": round(max(42.0, resting_heart_rate), 2),
        "stress_score": round(stress, 2),
        "mood_score": round(min(10.0, max(1.0, mood)), 2),
        "activity_confidence": round(
            min(10.0, max(1.0, activity_confidence)),
            2,
        ),
    }


def generate(seed: int, days: int, output: Path) -> None:
    """Generate ten deterministic personas with 30-60 days of data."""
    if not 30 <= days <= 60:
        raise ValueError("days must be between 30 and 60")

    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    output.mkdir(parents=True, exist_ok=True)

    profiles: list[dict[str, object]] = []
    observations: list[Observation] = []
    journals: list[dict[str, object]] = []
    goals: list[dict[str, object]] = []
    plans: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    feedback: list[dict[str, object]] = []
    truth: list[dict[str, object]] = []

    for persona_index in range(10):
        spec = _spec(persona_index)
        user_id = _uid(seed, f"persona-{persona_index}")
        profiles.append(
            _dump(
                UserProfile(
                    user_id=user_id,
                    age_band=spec.age_band,
                    preferred_language=spec.language,
                    timezone=spec.timezone,
                    schedule_constraints={
                        "weekend_pattern": "different_from_weekdays",
                    },
                    health_goals=DOMAINS,
                    coaching_preferences={
                        "baseline_adherence": round(spec.adherence, 3),
                    },
                    consent_flags={
                        "synthetic_data": True,
                        "evaluation_use": True,
                    },
                )
            )
        )

        goal_ids: dict[str, str] = {}
        for domain in DOMAINS:
            goal_id = _uid(seed, f"goal-{persona_index}-{domain}")
            goal_ids[domain] = goal_id
            goals.append(
                _dump(
                    Goal(
                        goal_id=goal_id,
                        user_id=user_id,
                        domain=domain,
                        description=(f"Maintain a sustainable {domain.replace('_', ' ')} routine"),
                        status="active",
                        created_at=start,
                        target_date=(start + timedelta(days=days - 1)).date(),
                    )
                )
            )

        plan_id = _uid(seed, f"plan-{persona_index}")
        plans.append(
            _dump(
                InterventionPlan(
                    plan_id=plan_id,
                    user_id=user_id,
                    goal_id=goal_ids["sleep"],
                    version=1,
                    start_date=start.date(),
                    end_date=(start + timedelta(days=days - 1)).date(),
                    status="active",
                    generation_interaction_id=_uid(
                        seed,
                        f"interaction-{persona_index}",
                    ),
                )
            )
        )

        action_ids: list[str] = []
        for domain in DOMAINS:
            action_id = _uid(seed, f"action-{persona_index}-{domain}")
            action_ids.append(action_id)
            actions.append(
                _dump(
                    PlanAction(
                        action_id=action_id,
                        plan_id=plan_id,
                        domain=domain,
                        description=(f"Follow the synthetic {domain.replace('_', ' ')} routine"),
                        frequency="daily",
                        difficulty=("low" if persona_index % 3 == 0 else "medium"),
                        rationale=("Synthetic action used to evaluate longitudinal adherence."),
                        status="accepted",
                    )
                )
            )

        change_start = days // 3 + persona_index % 4
        change_end = min(days - 1, change_start + 6)
        wearable_missing_start = days // 2 + persona_index % 3
        wearable_missing_end = min(
            days - 1,
            wearable_missing_start + 1 + persona_index % 2,
        )
        self_report_missing_start = min(
            days - 3,
            days * 2 // 3 + persona_index % 2,
        )
        self_report_missing_end = min(
            days - 1,
            self_report_missing_start + 1,
        )
        contradiction_day = 5 + persona_index % 4
        contradiction_id = _uid(seed, f"contradiction-{persona_index}")
        change_id = _uid(seed, f"change-{persona_index}")
        wearable_missing_id = _uid(
            seed,
            f"missing-wearable-{persona_index}",
        )
        self_report_missing_id = _uid(
            seed,
            f"missing-self-report-{persona_index}",
        )

        for day_index in range(days):
            observed_at = start + timedelta(days=day_index, hours=8)
            weekend = observed_at.weekday() >= 5
            change_window = change_start <= day_index <= change_end
            wearable_missing = wearable_missing_start <= day_index <= wearable_missing_end
            self_report_missing = self_report_missing_start <= day_index <= self_report_missing_end
            contradiction = day_index == contradiction_day
            values = _daily_values(
                rng,
                spec,
                day_index,
                days,
                weekend=weekend,
                change_window=change_window,
                contradiction=contradiction,
            )

            for metric_type in (
                "sleep_duration",
                "steps",
                "active_minutes",
                "resting_heart_rate",
                "activity_confidence",
            ):
                metadata: dict[str, object] = {
                    "day_index": day_index,
                    "persona_index": persona_index,
                    "synthetic": True,
                }
                if change_window:
                    metadata["change_event_id"] = change_id
                if contradiction and metric_type in {"sleep_duration", "steps"}:
                    metadata["contradiction_id"] = contradiction_id
                if wearable_missing:
                    metadata["missingness_id"] = wearable_missing_id
                    metadata["missingness_reason"] = "simulated_device_nonwear"
                observations.append(
                    _observation(
                        seed,
                        persona_index,
                        day_index,
                        metric_type,
                        user_id,
                        observed_at,
                        values[metric_type],
                        source_type="synthetic_wearable",
                        missing=wearable_missing,
                        metadata=metadata,
                    )
                )

            for metric_type in ("stress_score", "mood_score"):
                metadata = {
                    "day_index": day_index,
                    "persona_index": persona_index,
                    "synthetic": True,
                }
                if change_window:
                    metadata["change_event_id"] = change_id
                if self_report_missing:
                    metadata["missingness_id"] = self_report_missing_id
                    metadata["missingness_reason"] = "simulated_checkin_gap"
                observations.append(
                    _observation(
                        seed,
                        persona_index,
                        day_index,
                        metric_type,
                        user_id,
                        observed_at + timedelta(hours=12),
                        values[metric_type],
                        source_type="self_report",
                        missing=self_report_missing,
                        metadata=metadata,
                    )
                )

            if not self_report_missing:
                state = "routine"
                if change_window:
                    state = "stress"
                if contradiction:
                    state = "contradiction"
                tags = ["synthetic"]
                if change_window:
                    tags.append("change_point_window")
                if contradiction:
                    tags.extend(["synthetic_contradiction", contradiction_id])
                journals.append(
                    _dump(
                        JournalEntry(
                            entry_id=_uid(
                                seed,
                                f"journal-{persona_index}-{day_index}",
                            ),
                            user_id=user_id,
                            created_at=observed_at + timedelta(hours=13),
                            text=_journal_text(spec.language, state),
                            language=spec.language,
                            user_tags=tags,
                        )
                    )
                )

            if day_index % 7 == 6 or day_index == days - 1:
                adherence = spec.adherence + rng.uniform(-0.08, 0.04)
                if change_window:
                    adherence -= 0.28
                completion_ratio = round(min(1.0, max(0.0, adherence)), 2)
                response = "completed"
                if completion_ratio < 0.85:
                    response = "partially_completed"
                if completion_ratio < 0.4:
                    response = "not_completed"
                for action_id in action_ids:
                    feedback.append(
                        _dump(
                            PlanFeedback(
                                feedback_id=_uid(
                                    seed,
                                    (f"feedback-{persona_index}-{day_index}-{action_id}"),
                                ),
                                action_id=action_id,
                                user_id=user_id,
                                response=response,
                                completion_ratio=completion_ratio,
                                reason_text=(
                                    "Synthetic adherence decline during the injected stress event."
                                    if change_window
                                    else "Synthetic routine adherence check-in."
                                ),
                                created_at=observed_at + timedelta(hours=13),
                            )
                        )
                    )

        truth.append(
            {
                "persona_index": persona_index,
                "user_id": user_id,
                "change_point": {
                    "event_id": change_id,
                    "event": ("sleep_decline_stress_increase_activity_reduction"),
                    "start_day": change_start,
                    "end_day": change_end,
                    "effects": {
                        "plan_adherence": -0.28,
                        "sleep_duration_hours": -1.15,
                        "steps": -1800,
                        "stress_score": 2.0,
                    },
                },
                "missingness": [
                    {
                        "missingness_id": wearable_missing_id,
                        "modality": "wearable",
                        "reason": "simulated_device_nonwear",
                        "start_day": wearable_missing_start,
                        "end_day": wearable_missing_end,
                    },
                    {
                        "missingness_id": self_report_missing_id,
                        "modality": "self_report",
                        "reason": "simulated_checkin_gap",
                        "start_day": self_report_missing_start,
                        "end_day": self_report_missing_end,
                    },
                ],
                "contradictions": [
                    {
                        "contradiction_id": contradiction_id,
                        "day": contradiction_day,
                        "kind": "wearable_vs_journal_sleep_activity_conflict",
                        "journal_entry_id": _uid(
                            seed,
                            f"journal-{persona_index}-{contradiction_day}",
                        ),
                        "observation_ids": [
                            _uid(
                                seed,
                                (f"obs-{persona_index}-{contradiction_day}-sleep_duration"),
                            ),
                            _uid(
                                seed,
                                (f"obs-{persona_index}-{contradiction_day}-steps"),
                            ),
                        ],
                    }
                ],
                "periodicity": {
                    "period_days": 7,
                    "weekend_step_delta": spec.weekend_step_delta,
                },
                "trend": {
                    "activity_steps_per_day": spec.step_trend_per_day,
                    "sleep_hours_across_dataset": spec.sleep_trend_total,
                },
            }
        )

    _write_json(output / "profile.json", profiles)
    _write_json(output / "journal_entries.json", journals)
    _write_json(output / "goals.json", goals)
    _write_json(
        output / "intervention_history.json",
        {
            "actions": actions,
            "plan_feedback": feedback,
            "plans": plans,
        },
    )
    _write_json(
        output / "ground_truth.json",
        {
            "days": days,
            "design": {
                "correlations": [
                    "steps positively correlate with active_minutes",
                    "stress_score positively correlates with resting_heart_rate",
                    "stress_score negatively correlates with mood_score",
                ],
                "domains": DOMAINS,
                "privacy": "fully synthetic; no real-person or patient data",
                "schema": "CP-002 canonical models",
            },
            "personas": truth,
            "seed": seed,
        },
    )

    observation_path = output / "observations.csv"
    with observation_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OBSERVATION_FIELDS)
        writer.writeheader()
        for observation in observations:
            writer.writerow(_csv_row(observation))

    validate_generated_dataset(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Generate reproducible 30-60 day synthetic CarePath longitudinal data.")
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=45,
        help="Days per persona; must be between 30 and 60 inclusive.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated"),
        help="Output directory for generated files.",
    )
    args = parser.parse_args()
    generate(args.seed, args.days, args.output)


if __name__ == "__main__":
    main()
