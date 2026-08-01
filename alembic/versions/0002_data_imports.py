"""Add auditable health data import records.

Revision ID: 0002_data_imports
Revises: 0001_initial_storage
Create Date: 2026-07-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_data_imports"
down_revision = "0001_initial_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_imports",
        sa.Column("import_id", sa.String(36), primary_key=True),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("received_records", sa.Integer(), nullable=False),
        sa.Column("inserted_records", sa.Integer(), nullable=False),
        sa.Column("fixed_issues", sa.JSON(), nullable=False),
        sa.Column("skipped_records", sa.JSON(), nullable=False),
        sa.Column("blocking_errors", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "received_records >= 0",
            name="ck_data_imports_received_records",
        ),
        sa.CheckConstraint(
            "inserted_records >= 0",
            name="ck_data_imports_inserted_records",
        ),
    )
    op.create_index(
        "ix_data_imports_hash_time",
        "data_imports",
        ["source_hash", "imported_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_imports_hash_time", table_name="data_imports")
    op.drop_table("data_imports")
