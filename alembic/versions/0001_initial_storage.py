"""Create the initial CarePath storage schema.

Revision ID: 0001_initial_storage
Revises:
Create Date: 2026-07-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("age_band", sa.String(16), nullable=False),
        sa.Column("preferred_language", sa.String(8), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("schedule_constraints", sa.JSON(), nullable=True),
        sa.Column("health_goals", sa.JSON(), nullable=False),
        sa.Column("activity_constraints", sa.JSON(), nullable=True),
        sa.Column("coaching_preferences", sa.JSON(), nullable=True),
        sa.Column("consent_flags", sa.JSON(), nullable=False),
    )

    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("quality_flag", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_observations_confidence",
        ),
    )
    op.create_index(
        "ix_observations_user_metric_time",
        "observations",
        ["user_id", "metric_type", "observed_at"],
    )

    op.create_table(
        "journal_entries",
        sa.Column("entry_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("user_tags", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_journal_entries_user_created",
        "journal_entries",
        ["user_id", "created_at"],
    )

    op.create_table(
        "goals",
        sa.Column("goal_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
    )
    op.create_index("ix_goals_user_status", "goals", ["user_id", "status"])

    op.create_table(
        "interactions",
        sa.Column("interaction_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_level", sa.String(64), nullable=False),
        sa.Column("final_status", sa.String(64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_interactions_user_started",
        "interactions",
        ["user_id", "started_at"],
    )

    op.create_table(
        "intervention_plans",
        sa.Column("plan_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "goal_id",
            sa.String(36),
            sa.ForeignKey("goals.goal_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column(
            "generation_interaction_id",
            sa.String(36),
            sa.ForeignKey("interactions.interaction_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "supersedes_plan_id",
            sa.String(36),
            sa.ForeignKey("intervention_plans.plan_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("version >= 1", name="ck_intervention_plans_version"),
        sa.CheckConstraint("end_date >= start_date", name="ck_intervention_plans_dates"),
        sa.UniqueConstraint("goal_id", "version", name="uq_intervention_plans_goal_version"),
    )
    op.create_index(
        "ix_intervention_plans_user_status",
        "intervention_plans",
        ["user_id", "status"],
    )

    op.create_table(
        "plan_actions",
        sa.Column("action_id", sa.String(36), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("intervention_plans.plan_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(128), nullable=False),
        sa.Column("difficulty", sa.String(64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_plan_actions_plan_domain",
        "plan_actions",
        ["plan_id", "domain"],
    )

    op.create_table(
        "plan_feedback",
        sa.Column("feedback_id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("plan_actions.action_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("response", sa.String(64), nullable=False),
        sa.Column("completion_ratio", sa.Float(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "completion_ratio IS NULL OR (completion_ratio >= 0 AND completion_ratio <= 1)",
            name="ck_plan_feedback_completion_ratio",
        ),
    )
    op.create_index(
        "ix_plan_feedback_user_created",
        "plan_feedback",
        ["user_id", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", sa.String(36), primary_key=True),
        sa.Column(
            "interaction_id",
            sa.String(36),
            sa.ForeignKey("interactions.interaction_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("component", sa.String(128), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence_number >= 1", name="ck_audit_events_sequence_number"),
        sa.UniqueConstraint(
            "interaction_id",
            "sequence_number",
            name="uq_audit_events_interaction_sequence",
        ),
    )
    op.create_index(
        "ix_audit_events_interaction_created",
        "audit_events",
        ["interaction_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_interaction_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_plan_feedback_user_created", table_name="plan_feedback")
    op.drop_table("plan_feedback")
    op.drop_index("ix_plan_actions_plan_domain", table_name="plan_actions")
    op.drop_table("plan_actions")
    op.drop_index("ix_intervention_plans_user_status", table_name="intervention_plans")
    op.drop_table("intervention_plans")
    op.drop_index("ix_interactions_user_started", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("ix_goals_user_status", table_name="goals")
    op.drop_table("goals")
    op.drop_index("ix_journal_entries_user_created", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_index("ix_observations_user_metric_time", table_name="observations")
    op.drop_table("observations")
    op.drop_table("user_profiles")
