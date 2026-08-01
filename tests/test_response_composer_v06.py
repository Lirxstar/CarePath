from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.agents.context_builder import AdherenceContext, SignificantTrend, UserStateSummary
from backend.agents.response_composer import (
    CitationSourceType,
    ResponseComposer,
    ResponseStatement,
    StructuredCoachResponse,
    controlled_safety_response,
)
from backend.analysis_quality import ReliabilityLevel
from backend.domain.models import ActionDifficulty, MetricType, RiskLevel, TrustTier
from backend.personalization.planner_v2 import (
    GuidanceBasis,
    PersonalizedAction,
    PersonalizedWeeklyPlan,
    PlanAlternative,
)
from backend.retrieval.evidence import (
    ClaimScope,
    EvidenceBundle,
    EvidenceType,
    GroupedEvidenceItem,
)


def _summary() -> UserStateSummary:
    record_ids = (str(uuid4()), str(uuid4()), str(uuid4()))
    return UserStateSummary(
        user_id=uuid4(),
        generated_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        goals=("sleep: keep a regular sleep routine",),
        metrics_7d=(),
        metrics_30d=(),
        significant_trends=(
            SignificantTrend(
                metric_type=MetricType.SLEEP_DURATION,
                direction="decreased",
                current_mean=6.4,
                baseline_mean=7.2,
                percentage_change=-11.1,
                source_record_ids=record_ids,
            ),
        ),
        journal_themes=(),
        recent_actions=(),
        adherence=AdherenceContext(
            completion_rate=0.7,
            recent_completion_rate=0.6,
            scored_feedback_count=3,
            total_feedback_count=3,
            reliability=ReliabilityLevel.HIGH,
            source_record_ids=(),
        ),
        preferences={},
        constraints={},
        facts=(),
        subjective_descriptions=(),
        inferences=(),
        data_insufficient=(),
        source_record_ids=record_ids,
    )


def _evidence() -> EvidenceBundle:
    return EvidenceBundle(
        patient_evidence=(),
        external_evidence=(
            GroupedEvidenceItem(
                evidence_id="external:chunk-sleep",
                evidence_type=EvidenceType.EXTERNAL_GUIDELINE,
                claim_scope=ClaimScope.GENERAL_GUIDANCE,
                content="Keep a regular sleep schedule to support healthy sleep habits.",
                source_ids=("src-sleep", "chunk-sleep"),
                trust_tier=TrustTier.GUIDELINE,
                relevance_score=0.9,
                citation="Public Sleep Agency — Sleep habits — chunk-sleep",
            ),
        ),
    )


def _plan() -> PersonalizedWeeklyPlan:
    start = date(2026, 7, 30)
    alternatives = (
        PlanAlternative(description="Use a two-minute version.", reason="lower effort"),
        PlanAlternative(description="Keep only the wake-time cue.", reason="alternate route"),
    )
    actions = tuple(
        PersonalizedAction(
            scheduled_date=start + timedelta(days=index),
            description="Use five minutes for a consistent wind-down cue before sleep.",
            frequency="once that day",
            difficulty=ActionDifficulty.LOW,
            rationale="A small action fits the current context.",
            evidence_ids=("external:chunk-sleep",),
            follow_up_condition="Review comfort and completion after seven days.",
            alternatives=alternatives,
            guidance_basis=GuidanceBasis.EVIDENCE_GROUNDED,
        )
        for index in range(7)
    )
    return PersonalizedWeeklyPlan(
        goal="sleep: keep a regular sleep routine",
        actions=actions,
        frequency="one small action daily for seven days",
        difficulty=ActionDifficulty.LOW,
        rationale="Use a small evidence-grounded step.",
        evidence_ids=("external:chunk-sleep",),
        follow_up_condition="Review comfort and completion after seven days.",
        alternatives=alternatives,
        data_limited=False,
        context_source_record_ids=_summary().source_record_ids,
    )


def test_composer_returns_fixed_six_sections_with_resolvable_exact_citations() -> None:
    response = ResponseComposer().compose(
        summary=_summary(),
        plan=_plan(),
        evidence=_evidence(),
        risk_level=RiskLevel.ROUTINE,
        language="en",
    )

    assert response.what_i_noticed
    assert response.what_the_evidence_suggests
    assert len(response.realistic_plan_for_this_week) == 7
    assert response.when_to_seek_professional_help
    assert response.sources
    assert response.what_i_am_uncertain_about
    assert "What I noticed" in response.rendered_text
    assert "Sources" in response.rendered_text

    by_id = {source.citation_id: source for source in response.sources}
    referenced = {
        citation_id
        for item in (*response.what_i_noticed, *response.what_the_evidence_suggests)
        for citation_id in item.citation_ids
    }
    referenced.update(
        citation_id
        for action in response.realistic_plan_for_this_week
        for citation_id in action.citation_ids
    )
    assert referenced <= by_id.keys()
    guideline = next(
        source
        for source in response.sources
        if source.source_type is CitationSourceType.EXTERNAL_GUIDELINE
    )
    assert guideline.source_id == "src-sleep"
    assert guideline.chunk_id == "chunk-sleep"
    assert guideline.display_citation
    assert "Keep a regular sleep schedule" in response.what_the_evidence_suggests[0].text


def test_multilingual_rendering_preserves_risk_and_safety_conclusion() -> None:
    responses = [
        controlled_safety_response(risk_level=RiskLevel.URGENT, language=language)
        for language in ("en", "zh", "ja")
    ]

    assert {response.risk_level for response in responses} == {RiskLevel.URGENT}
    assert all(not response.realistic_plan_for_this_week for response in responses)
    assert all(response.when_to_seek_professional_help for response in responses)
    assert all(response.what_i_am_uncertain_about for response in responses)


def test_structured_response_rejects_unresolvable_pseudo_citation() -> None:
    with pytest.raises(ValidationError, match="unresolved citation"):
        StructuredCoachResponse(
            language="en",
            risk_level=RiskLevel.ROUTINE,
            what_i_noticed=(
                ResponseStatement(
                    statement_id="noticed-1",
                    text="Observed change.",
                    citation_ids=("missing-citation",),
                ),
            ),
            what_the_evidence_suggests=(),
            realistic_plan_for_this_week=(),
            when_to_seek_professional_help=("Seek help if concerns persist.",),
            sources=(),
            what_i_am_uncertain_about=("Cause is unknown.",),
            rendered_text="Structured response",
        )
