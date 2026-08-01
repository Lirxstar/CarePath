from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

UUID_LENGTH = 36
ENUM_LENGTH = 64


class DataImportTable(Base):
    __tablename__ = "data_imports"

    import_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    received_records: Mapped[int] = mapped_column(Integer, nullable=False)
    inserted_records: Mapped[int] = mapped_column(Integer, nullable=False)
    fixed_issues: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    skipped_records: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    blocking_errors: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        CheckConstraint("received_records >= 0", name="ck_data_imports_received_records"),
        CheckConstraint("inserted_records >= 0", name="ck_data_imports_inserted_records"),
        Index("ix_data_imports_hash_time", "source_hash", "imported_at"),
    )


class UserProfileTable(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    age_band: Mapped[str] = mapped_column(String(16), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule_constraints: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    health_goals: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    activity_constraints: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    coaching_preferences: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    consent_flags: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False)


class ObservationTable(Base):
    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(ENUM_LENGTH), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    quality_flag: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_observations_confidence",
        ),
        Index("ix_observations_user_metric_time", "user_id", "metric_type", "observed_at"),
    )


class JournalEntryTable(Base):
    __tablename__ = "journal_entries"

    entry_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    user_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_journal_entries_user_created", "user_id", "created_at"),)


class GoalTable(Base):
    __tablename__ = "goals"

    goal_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (Index("ix_goals_user_status", "user_id", "status"),)


class InteractionTable(Base):
    __tablename__ = "interactions"

    interaction_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    final_status: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_interactions_user_started", "user_id", "started_at"),)


class InterventionPlanTable(Base):
    __tablename__ = "intervention_plans"

    plan_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.goal_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    generation_interaction_id: Mapped[str] = mapped_column(
        ForeignKey("interactions.interaction_id", ondelete="RESTRICT"), nullable=False
    )
    supersedes_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("intervention_plans.plan_id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_intervention_plans_version"),
        CheckConstraint("end_date >= start_date", name="ck_intervention_plans_dates"),
        UniqueConstraint("goal_id", "version", name="uq_intervention_plans_goal_version"),
        Index("ix_intervention_plans_user_status", "user_id", "status"),
    )


class PlanActionTable(Base):
    __tablename__ = "plan_actions"

    action_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("intervention_plans.plan_id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str] = mapped_column(String(128), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)

    __table_args__ = (Index("ix_plan_actions_plan_domain", "plan_id", "domain"),)


class PlanFeedbackTable(Base):
    __tablename__ = "plan_feedback"

    feedback_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    action_id: Mapped[str] = mapped_column(
        ForeignKey("plan_actions.action_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    response: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    completion_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "completion_ratio IS NULL OR (completion_ratio >= 0 AND completion_ratio <= 1)",
            name="ck_plan_feedback_completion_ratio",
        ),
        Index("ix_plan_feedback_user_created", "user_id", "created_at"),
    )


class AuditEventTable(Base):
    __tablename__ = "audit_events"

    audit_event_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(
        ForeignKey("interactions.interaction_id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    component: Mapped[str] = mapped_column(String(128), nullable=False)
    input_refs: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    output_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("sequence_number >= 1", name="ck_audit_events_sequence_number"),
        UniqueConstraint(
            "interaction_id", "sequence_number", name="uq_audit_events_interaction_sequence"
        ),
        Index("ix_audit_events_interaction_created", "interaction_id", "created_at"),
    )
