"""add_report_to_agent_findings

Revision ID: c4b1a7e8d9f0
Revises: f2a1c9d8e7b6
Create Date: 2026-03-13 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4b1a7e8d9f0"
down_revision = "f2a1c9d8e7b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_findings", sa.Column("report", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_findings", "report")
