"""add agent finding identity column

Revision ID: 8c1d2e3f4a5b
Revises: 7f8e9d0c1b2a
Create Date: 2026-03-15 11:30:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8c1d2e3f4a5b"
down_revision = "7f8e9d0c1b2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_findings
        ADD COLUMN IF NOT EXISTS finding_identity VARCHAR(128)
        """
    )
    op.execute(
        """
        UPDATE agent_findings
        SET finding_identity = COALESCE(
            NULLIF(finding_metadata->>'finding_identity', ''),
            NULLIF(verification_result->>'finding_identity', '')
        )
        WHERE finding_identity IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_findings_finding_identity
        ON agent_findings (finding_identity)
        """
    )


def downgrade() -> None:
    pass
