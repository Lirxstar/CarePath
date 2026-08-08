from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from backend.agents.context_builder import AdherenceContext, MetricWindowSummary, UserStateSummary
from backend.analysis_quality import AnalysisReliability, ReliabilityLevel
from backend.domain.models import MetricType
from backend.personalization.planner_v2 import GuidanceBasis, PersonalizedInterventionPlanner
from backend.retrieval.evidence import (
    ClaimScope,
    EvidenceAggregator,
    EvidenceType,
    ToolEvidenceFact,
)
from backend.retrieval.patient import PatientEvidenceItem, PatientEvidenceKind
from backend.retrieval.vector import ExternalEvidenceHit, ExternalEvidenceMetadata


def _external_hit(*, chunk_id: str = "activity-1", score: float = 0.9) -> ExternalEvidenceHit:
    metadata = ExternalEvidenceMetadata(
        chunk_id=chunk_id,
        source_id="source-activity",
        title="Physical activity guidance",
        canonical_url="https://example.org/activity",
        retrieved_at=date(2026, 7, 30),
        language="en",
        topics=("physical_activity",),
        organisation="Public Health Example",
        license="public information",
        source_content_hash="a" * 64,
        content_hash="b" * 64,
        ingestion_version="test-v1",
        embedding_model="test-embedding",
    )
    return ExternalEvidenceHit(
        chunk_id=chunk_id,
        score=score,
        content="Regular walking and other physical activity can be built up gradually.",
        metadata=metadata,
        citation="Public Health Example — Physical activity guidance",
    )


def test_evidence_aggregator_preserves_claim_boundaries_and_deduplicates() -> None:
    reliability = AnalysisReliability(level=ReliabilityLevel.HIGH)
    journal = PatientEvidenceItem(
        evidence_id="patient:journal:j1",
        kind=PatientEvidenceKind.SUBJECTIVE_DESCRIPTION,
        fact="User reported that sleep felt difficult.",
        source_record_ids=("j1",),
        reliability=reliability,
    )
    tool_fact = ToolEvidenceFact(
        evidence_id="patient:tool:steps-7d",
        content="Steps 7-day tool summary shows a recent measured pattern.",
        source_record_ids=("o1", "o2"),
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 30),
    )
    aggregator = EvidenceAggregator(min_external_score=0.05)
    bundle = aggregator.build(
        patient_items=(journal, journal),
        tool_facts=(tool_fact,),
        external_hits=(_external_hit(), _external_hit(chunk_id="low", score=0.01)),
    )

    assert len(bundle.patient_evidence) == 2
    assert len(bundle.external_evidence) == 1
    reported = bundle.by_id("patient:journal:j1")
    assert reported is not None
    assert reported.evidence_type is EvidenceType.USER_REPORT
    assert reported.claim_scope is ClaimScope.USER_REPORTED
    guideline = bundle.external_evidence[0]
    assert guideline.evidence_type is EvidenceType.EXTERNAL_GUIDELINE
    assert guideline.claim_scope is ClaimScope.GENERAL_GUIDANCE
    assert guideline.evidence_id == "external:activity-1"


def _metric(metric: MetricType, mean: float) -> MetricWindowSummary:
    return MetricWindowSummary(
        metric_type=metric,
        window_days=7,
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 30),
        mean=mean,
        slope_per_day=0.0,
        coverage=1.0,
        missing_rate=0.0,
        sample_count=7,
        expected_count=7,
        reliability=ReliabilityLevel.HIGH,
        data_sufficient=True,
        source_record_ids=(f"{metric.value}-1",),
    )


def _summary(
    *,
    completion: float | None,
    scored_feedback_count: int = 7,
    total_feedback_count: int = 7,
    reliability: ReliabilityLevel = ReliabilityLevel.HIGH,
) -> UserStateSummary:
    user_id = uuid4()
    adherence = AdherenceContext(
        completion_rate=completion,
        recent_completion_rate=completion,
        scored_feedback_count=scored_feedback_count,
        total_feedback_count=total_feedback_count,
        reliability=reliability,
        source_record_ids=("feedback-1",),
    )
    return UserStateSummary(
        user_id=user_id,
        generated_at=datetime(2026, 7, 30, 20, tzinfo=UTC),
        goals=("physical_activity: Build a sustainable activity routine",),
        metrics_7d=(_metric(MetricType.STEPS, 6500.0), _metric(MetricType.STRESS_SCORE, 4.0)),
        metrics_30d=(),
        significant_trends=(),
        journal_themes=(),
        recent_actions=("Short walk",),
        adherence=adherence,
        preferences={"style": "brief"},
        constraints={"weekday_evening_minutes": 20},
        facts=(),
        subjective_descriptions=(),
        inferences=(),
        data_insufficient=(),
        source_record_ids=("profile-1", "feedback-1"),
    )


def test_planner_v2_is_schema_valid_evidence_aware_and_reduces_low_adherence() -> None:
    evidence = EvidenceAggregator().build(
        external_hits=(_external_hit(),),
        tool_facts=(
            ToolEvidenceFact(
                evidence_id="patient:tool:steps",
                content="Steps trend from measured user observations.",
                source_record_ids=("steps-1",),
            ),
        ),
    )
    planner = PersonalizedInterventionPlanner()
    high = planner.plan(
        summary=_summary(completion=0.95),
        evidence=evidence,
        start_date=date(2026, 7, 31),
        request_text="Build a physical activity plan",
    )
    low = planner.plan(
        summary=_summary(completion=0.30),
        evidence=evidence,
        start_date=date(2026, 7, 31),
        request_text="Build a physical activity plan",
    )

    assert high.duration_days == 7
    assert len(high.actions) == 7
    assert high.difficulty.value == "medium"
    assert low.difficulty.value == "low"
    assert high.actions[0].description != low.actions[0].description
    assert "20-minute" in high.actions[0].description
    assert "Take an 8-minute" in low.actions[0].description
    assert all(action.guidance_basis is GuidanceBasis.EVIDENCE_GROUNDED for action in high.actions)
    assert "external:activity-1" in high.evidence_ids
    assert all(action.alternatives for action in high.actions)
    assert "completion" in low.rationale


def test_planner_v2_accept_feedback_maintains_scope_with_explanation() -> None:
    planner = PersonalizedInterventionPlanner()
    accepted = planner.plan(
        summary=_summary(
            completion=None,
            scored_feedback_count=0,
            total_feedback_count=1,
            reliability=ReliabilityLevel.HIGH,
        ),
        evidence=EvidenceAggregator().build(external_hits=(_external_hit(),)),
        start_date=date(2026, 7, 31),
        request_text="Build a physical activity plan",
    )
    no_feedback = planner.plan(
        summary=_summary(
            completion=None,
            scored_feedback_count=0,
            total_feedback_count=0,
            reliability=ReliabilityLevel.HIGH,
        ),
        evidence=EvidenceAggregator().build(external_hits=(_external_hit(),)),
        start_date=date(2026, 7, 31),
        request_text="Build a physical activity plan",
    )

    assert accepted.difficulty == no_feedback.difficulty
    assert accepted.actions[0].description == no_feedback.actions[0].description
    assert "accepted feedback supports maintaining" in accepted.rationale
    assert accepted.rationale != no_feedback.rationale


def test_planner_v2_labels_unreferenced_fallback_as_general_low_risk() -> None:
    plan = PersonalizedInterventionPlanner().plan(
        summary=_summary(completion=0.8),
        evidence=EvidenceAggregator().build(),
        start_date=date(2026, 7, 31),
        request_text="Build a physical activity plan",
    )

    assert plan.evidence_ids == ()
    assert all(action.guidance_basis is GuidanceBasis.GENERAL_LOW_RISK for action in plan.actions)
    text = plan.model_dump_json().casefold()
    assert "diagnos" not in text
    assert "medication" not in text
    assert "treat" not in text
