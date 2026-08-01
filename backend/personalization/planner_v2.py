"""Evidence-aware personalized seven-day behavioural planner."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.agents.context_builder import UserStateSummary
from backend.domain.models import ActionDifficulty, Domain, MetricType
from backend.retrieval.evidence import ClaimScope, EvidenceBundle


class GuidanceBasis(StrEnum):
    EVIDENCE_GROUNDED = "evidence_grounded"
    GENERAL_LOW_RISK = "general_low_risk"


class PlanAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PersonalizedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scheduled_date: date
    description: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    difficulty: ActionDifficulty
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    follow_up_condition: str = Field(min_length=1)
    alternatives: tuple[PlanAlternative, ...]
    guidance_basis: GuidanceBasis

    @model_validator(mode="after")
    def evidence_required_when_claimed(self) -> Self:
        if self.guidance_basis is GuidanceBasis.EVIDENCE_GROUNDED and not self.evidence_ids:
            raise ValueError("evidence-grounded actions require evidence_ids")
        return self


class PersonalizedWeeklyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1)
    actions: tuple[PersonalizedAction, ...]
    frequency: str = Field(min_length=1)
    difficulty: ActionDifficulty
    duration_days: Literal[7] = 7
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[str, ...]
    follow_up_condition: str = Field(min_length=1)
    alternatives: tuple[PlanAlternative, ...]
    data_limited: bool
    context_source_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_week(self) -> Self:
        if len(self.actions) != 7:
            raise ValueError("weekly plan must contain exactly seven daily actions")
        expected = {self.actions[0].scheduled_date + timedelta(days=index) for index in range(7)}
        if {item.scheduled_date for item in self.actions} != expected:
            raise ValueError("weekly plan actions must cover seven consecutive days")
        known = set(self.evidence_ids)
        if any(set(item.evidence_ids) - known for item in self.actions):
            raise ValueError("action evidence_ids must be declared by the plan")
        return self


_DOMAIN_TERMS: dict[Domain, tuple[str, ...]] = {
    Domain.SLEEP: ("sleep", "bed", "wake", "睡", "眠"),
    Domain.PHYSICAL_ACTIVITY: (
        "walk",
        "step",
        "activity",
        "exercise",
        "步",
        "运动",
        "歩",
        "運動",
    ),
    Domain.STRESS_MOOD: ("stress", "mood", "pressure", "压力", "情绪", "ストレス", "気分"),
    Domain.FALLS_ACTIVITY_SAFETY: ("fall", "balance", "trip", "跌倒", "摔倒", "転倒"),
}


def _minute_article(minutes: int) -> str:
    return "an" if minutes in {8, 11, 18} else "a"


_DOMAIN_METRIC: dict[Domain, MetricType] = {
    Domain.SLEEP: MetricType.SLEEP_DURATION,
    Domain.PHYSICAL_ACTIVITY: MetricType.STEPS,
    Domain.STRESS_MOOD: MetricType.STRESS_SCORE,
    Domain.FALLS_ACTIVITY_SAFETY: MetricType.ACTIVITY_CONFIDENCE,
}


class PersonalizedInterventionPlanner:
    """Create bounded low-risk plans from state summaries and explicitly typed evidence."""

    def plan(
        self,
        *,
        summary: UserStateSummary,
        evidence: EvidenceBundle,
        start_date: date,
        request_text: str,
    ) -> PersonalizedWeeklyPlan:
        domain = self._domain(summary, request_text)
        completion = summary.adherence.recent_completion_rate
        if completion is None:
            completion = summary.adherence.completion_rate
        profile_adherence = summary.preferences.get("baseline_adherence")
        if (
            completion is None
            and isinstance(profile_adherence, (int, float))
            and not isinstance(profile_adherence, bool)
        ):
            completion = max(0.0, min(1.0, float(profile_adherence)))

        metric = summary.metric(_DOMAIN_METRIC[domain], 7)
        data_limited = metric is None or not metric.data_sufficient
        stressed = self._high_recent_stress(summary)
        available_minutes = self._available_minutes(summary)
        difficulty, minutes = self._scope(
            completion=completion,
            data_limited=data_limited,
            stressed=stressed,
            available_minutes=available_minutes,
        )
        external_ids = tuple(
            item.evidence_id
            for item in evidence.external_evidence
            if item.claim_scope is ClaimScope.GENERAL_GUIDANCE
            and self._matches_domain(item.content, domain)
        )[:2]
        patient_ids = tuple(
            item.evidence_id
            for item in evidence.patient_evidence
            if self._matches_domain(item.content, domain)
        )[:2]
        evidence_ids = tuple(dict.fromkeys((*external_ids, *patient_ids)))
        basis = GuidanceBasis.EVIDENCE_GROUNDED if external_ids else GuidanceBasis.GENERAL_LOW_RISK
        description = self._description(
            domain, minutes, bool(summary.constraints.get("activity_constraints"))
        )
        rationale = self._rationale(completion, data_limited, stressed, basis)
        follow_up = (
            "Review completion and comfort after seven days; scale the next plan down "
            "if completion is low, and pause any action that conflicts with a professional "
            "restriction or feels unsafe."
        )
        alternatives = self._alternatives(domain, minutes)
        actions = tuple(
            PersonalizedAction(
                scheduled_date=start_date + timedelta(days=index),
                description=description,
                frequency="once that day",
                difficulty=difficulty,
                rationale=rationale,
                evidence_ids=evidence_ids,
                follow_up_condition=follow_up,
                alternatives=alternatives,
                guidance_basis=basis,
            )
            for index in range(7)
        )
        goal = self._goal(summary, domain)
        return PersonalizedWeeklyPlan(
            goal=goal,
            actions=actions,
            frequency="one small action daily for seven days",
            difficulty=difficulty,
            rationale=rationale,
            evidence_ids=evidence_ids,
            follow_up_condition=follow_up,
            alternatives=alternatives,
            data_limited=data_limited,
            context_source_record_ids=summary.source_record_ids,
        )

    @staticmethod
    def _domain(summary: UserStateSummary, request_text: str) -> Domain:
        text = request_text.casefold()
        for domain, terms in _DOMAIN_TERMS.items():
            if any(term in text for term in terms):
                return domain
        for goal in summary.goals:
            prefix = goal.split(":", 1)[0]
            try:
                return Domain(prefix)
            except ValueError:
                continue
        return Domain.SLEEP

    @staticmethod
    def _goal(summary: UserStateSummary, domain: Domain) -> str:
        prefix = f"{domain.value}:"
        return next(
            (goal for goal in summary.goals if goal.startswith(prefix)),
            f"Build a sustainable {domain.value} routine",
        )

    @staticmethod
    def _high_recent_stress(summary: UserStateSummary) -> bool:
        stress = summary.metric(MetricType.STRESS_SCORE, 7)
        return (
            stress is not None
            and stress.data_sufficient
            and stress.mean is not None
            and stress.mean >= 7.0
        )

    @staticmethod
    def _available_minutes(summary: UserStateSummary) -> int:
        values = [
            int(value)
            for value in summary.constraints.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        ]
        return min(values) if values else 15

    @staticmethod
    def _scope(
        *,
        completion: float | None,
        data_limited: bool,
        stressed: bool,
        available_minutes: int,
    ) -> tuple[ActionDifficulty, int]:
        low_adherence = completion is not None and completion < 0.6
        high_adherence = completion is not None and completion >= 0.85
        if low_adherence or data_limited or stressed:
            return ActionDifficulty.LOW, max(3, min(8, available_minutes))
        if high_adherence and available_minutes >= 15:
            return ActionDifficulty.MEDIUM, min(20, available_minutes)
        return ActionDifficulty.LOW, max(5, min(12, available_minutes))

    @staticmethod
    def _description(domain: Domain, minutes: int, activity_limited: bool) -> str:
        if domain is Domain.SLEEP:
            return (
                f"Use {minutes} minutes for a consistent wind-down cue before your intended "
                "sleep period."
            )
        if domain is Domain.PHYSICAL_ACTIVITY:
            if activity_limited:
                return (
                    f"Choose {minutes} minutes of comfortable movement that stays within your "
                    "stated activity constraints."
                )
            return (
                f"Take {_minute_article(minutes)} {minutes}-minute comfortable walk "
                "or equivalent light movement break."
            )
        if domain is Domain.STRESS_MOOD:
            return (
                f"Take {_minute_article(minutes)} {minutes}-minute quiet recovery break using "
                "paced breathing or another "
                "preferred calming routine."
            )
        return (
            f"Spend {minutes} minutes checking one commonly used walking area for avoidable "
            "trip hazards."
        )

    @staticmethod
    def _rationale(
        completion: float | None,
        data_limited: bool,
        stressed: bool,
        basis: GuidanceBasis,
    ) -> str:
        reasons: list[str] = []
        if completion is not None and completion < 0.6:
            reasons.append("recent structured completion was low, so the action was reduced")
        if stressed:
            reasons.append("recent stress data were high, so workload was kept small")
        if data_limited:
            reasons.append("recent data were incomplete, so the plan stays conservative")
        if not reasons:
            reasons.append(
                "the action is scaled to the available user context and prior completion history"
            )
        grounding = (
            "general guidance is supported by retrieved external evidence"
            if basis is GuidanceBasis.EVIDENCE_GROUNDED
            else "the suggestion is explicitly marked as general low-risk behavioural guidance"
        )
        return f"{' ; '.join(reasons)}; {grounding}."

    @staticmethod
    def _alternatives(domain: Domain, minutes: int) -> tuple[PlanAlternative, ...]:
        shorter = max(2, minutes // 2)
        if domain is Domain.SLEEP:
            other = "Prepare the sleep environment and keep the same wake-time cue instead."
        elif domain is Domain.PHYSICAL_ACTIVITY:
            other = "Break the movement into two brief comfortable sessions instead."
        elif domain is Domain.STRESS_MOOD:
            other = "Use a quiet screen-free pause or brief written reflection instead."
        else:
            other = "Review lighting and clear one small walking path instead."
        return (
            PlanAlternative(
                description=(
                    f"Use {_minute_article(shorter)} {shorter}-minute version of the same action."
                ),
                reason="lower-effort fallback when time or energy is limited",
            ),
            PlanAlternative(
                description=other, reason="different low-risk route toward the same goal"
            ),
        )

    @staticmethod
    def _matches_domain(content: str, domain: Domain) -> bool:
        text = content.casefold()
        return any(term in text for term in _DOMAIN_TERMS[domain])
