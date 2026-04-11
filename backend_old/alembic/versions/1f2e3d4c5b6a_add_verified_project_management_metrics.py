"""add verified project management metrics

Revision ID: 1f2e3d4c5b6a
Revises: f6a7b8c9d0e1
Create Date: 2026-03-24 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_management_metrics",
        sa.Column("verified_critical", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_management_metrics",
        sa.Column("verified_high", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_management_metrics",
        sa.Column("verified_medium", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_management_metrics",
        sa.Column("verified_low", sa.Integer(), nullable=False, server_default="0"),
    )

    op.alter_column(
        "project_management_metrics",
        "verified_critical",
        server_default=None,
    )
    op.alter_column(
        "project_management_metrics",
        "verified_high",
        server_default=None,
    )
    op.alter_column(
        "project_management_metrics",
        "verified_medium",
        server_default=None,
    )
    op.alter_column(
        "project_management_metrics",
        "verified_low",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("project_management_metrics", "verified_low")
    op.drop_column("project_management_metrics", "verified_medium")
    op.drop_column("project_management_metrics", "verified_high")
    op.drop_column("project_management_metrics", "verified_critical")
