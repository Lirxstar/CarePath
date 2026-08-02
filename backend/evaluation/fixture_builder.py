from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from backend.evaluation.scenarios import EvaluationScenario, load_scenario_set


class EvaluationFixture(BaseModel):
    """Scenario facts used to build a synthetic user, never passed to the agent prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    persona_id: str
    language: str
    context_text: str
    personal_evidence_refs: tuple[str, ...]
    external_evidence_refs: tuple[str, ...]
    observation_refs: tuple[str, ...]
    journal_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    plan_refs: tuple[str, ...]
    feedback_refs: tuple[str, ...]
    event_refs: tuple[str, ...]
    quality_refs: tuple[str, ...]


def build_evaluation_fixture(scenario: EvaluationScenario) -> EvaluationFixture:
    personal = scenario.expected_evidence.personal
    return EvaluationFixture(
        scenario_id=scenario.scenario_id,
        persona_id=scenario.persona_id,
        language=scenario.language.value,
        context_text=" ".join(scenario.context_overrides),
        personal_evidence_refs=personal,
        external_evidence_refs=scenario.expected_evidence.external,
        observation_refs=_with_prefix(personal, "observation:"),
        journal_refs=_with_prefix(personal, "journal:"),
        profile_refs=_with_prefix(personal, "profile:"),
        plan_refs=_with_prefix(personal, "plan:"),
        feedback_refs=_with_prefix(personal, "feedback:"),
        event_refs=_with_prefix(personal, "event:"),
        quality_refs=_with_prefix(personal, "quality_flag:"),
    )


@lru_cache(maxsize=96)
def fixture_for_scenario(scenario_id: str) -> EvaluationFixture:
    scenario = next(
        (item for item in load_scenario_set().scenarios if item.scenario_id == scenario_id),
        None,
    )
    if scenario is not None:
        return build_evaluation_fixture(scenario)
    return EvaluationFixture(
        scenario_id=scenario_id,
        persona_id="redteam_synthetic",
        language="en",
        context_text="Synthetic red-team fixture.",
        personal_evidence_refs=("journal:recent",),
        external_evidence_refs=("topic:when_to_seek_professional_help",),
        observation_refs=(),
        journal_refs=("journal:recent",),
        profile_refs=(),
        plan_refs=(),
        feedback_refs=(),
        event_refs=(),
        quality_refs=(),
    )


def external_evidence_content(reference: str, context_text: str) -> str:
    label = reference.split(":", 1)[-1].replace("_", " ")
    if reference.startswith("untrusted_document:"):
        return context_text
    return (
        f"Synthetic evaluation guidance about {label}. "
        "Use gradual, non-diagnostic behaviour support, respect user constraints, "
        "acknowledge uncertainty, and recommend professional review when concerns persist."
    )


def _with_prefix(values: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    return tuple(value for value in values if value.startswith(prefix))
