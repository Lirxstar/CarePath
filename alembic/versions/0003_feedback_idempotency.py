"""Add feedback submission idempotency keys.

Revision ID: 0003_feedback_idempotency
Revises: 0002_data_imports
Create Date: 2026-08-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_feedback_idempotency"
down_revision = "0002_data_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plan_feedback",
        sa.Column("submission_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_plan_feedback_user_submission_key",
        "plan_feedback",
        ["user_id", "submission_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_plan_feedback_user_submission_key", table_name="plan_feedback")
    op.drop_column("plan_feedback", "submission_key")
