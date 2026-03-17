"""add project management metrics table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-17 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_management_metrics",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("archive_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("archive_original_filename", sa.String(), nullable=True),
        sa.Column("archive_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audit_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opengrep_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gitleaks_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bandit_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phpstan_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_completed_task_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("project_management_metrics")
