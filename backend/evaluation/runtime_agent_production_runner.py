from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid5

from backend.storage.models import (
    GoalTable,
    JournalEntryTable,
    ObservationTable,
    UserProfileTable,
)

from .complete_models import BenchmarkRequest
from .complete_scenarios import _security_attack_text
from .runtime_agent_runner import _EVALUATION_END, _EVALUATION_NAMESPACE
from .runtime_agent_runner import RuntimeAgentBaselineRunner as _RuntimeAgentBaselineRunner


class RuntimeAgentBaselineRunner(_RuntimeAgentBaselineRunner):
    """Production B3 runner with explicit parent-before-child fixture persistence."""

    def _seed_user(self, request: BenchmarkRequest, user_id: UUID) -> None:
        if self.session.get(UserProfileTable, str(user_id)) is not None:
            return

        self.session.add(
            UserProfileTable(
                user_id=str(user_id),
                age_band="30-44",
                preferred_language=request.language.value,
                timezone="UTC",
                schedule_constraints={"weekday_evening_minutes": 15},
                health_goals=["sleep", "physical_activity", "stress_mood"],
                activity_constraints=None,
                coaching_preferences={"style": "brief", "baseline_adherence": 0.72},
                consent_flags={"synthetic_demo": True},
            )
        )
        self.session.flush()

        for domain, description in (
            ("sleep", "Build a regular sleep routine"),
            ("physical_activity", "Maintain comfortable daily movement"),
            ("stress_mood", "Use manageable recovery breaks"),
        ):
            self.session.add(
                GoalTable(
                    goal_id=str(
                        uuid5(_EVALUATION_NAMESPACE, f"goal:{request.scenario_id}:{domain}")
                    ),
                    user_id=str(user_id),
                    domain=domain,
                    description=description,
                    status="active",
                    created_at=_EVALUATION_END - timedelta(days=30),
                    target_date=None,
                )
            )

        request_text = _security_attack_text(request)
        missing_pattern = any(
            term in request_text for term in ("missing", "gap", "blank", "drop out")
        )
        suspect_steps = "45,000" in request_text
        for index in range(30):
            observed_at = _EVALUATION_END - timedelta(days=29 - index)
            if missing_pattern and 10 <= index <= 15:
                continue
            for metric, value, unit, quality in self._daily_values(
                index, suspect_steps=suspect_steps
            ):
                self.session.add(
                    ObservationTable(
                        observation_id=str(
                            uuid5(
                                _EVALUATION_NAMESPACE,
                                f"observation:{request.scenario_id}:{metric}:{index}",
                            )
                        ),
                        user_id=str(user_id),
                        metric_type=metric,
                        value_numeric=value,
                        value_boolean=None,
                        unit=unit,
                        observed_at=observed_at,
                        source_type="synthetic_wearable",
                        quality_flag=quality,
                        confidence=0.95,
                        metadata_json={"scenario_id": request.scenario_id},
                    )
                )

        self.session.add(
            JournalEntryTable(
                entry_id=str(
                    uuid5(_EVALUATION_NAMESPACE, f"journal:{request.scenario_id}:context")
                ),
                user_id=str(user_id),
                created_at=_EVALUATION_END - timedelta(hours=2),
                text=" ".join(request.context_overrides),
                language=request.language.value,
                user_tags=["evaluation", "synthetic"],
            )
        )
        if request.hostile_document:
            self.session.add(
                JournalEntryTable(
                    entry_id=str(
                        uuid5(_EVALUATION_NAMESPACE, f"journal:{request.scenario_id}:hostile")
                    ),
                    user_id=str(user_id),
                    created_at=_EVALUATION_END - timedelta(hours=1),
                    text=request.hostile_document,
                    language=request.language.value,
                    user_tags=["evaluation", "untrusted"],
                )
            )
        self.session.commit()
