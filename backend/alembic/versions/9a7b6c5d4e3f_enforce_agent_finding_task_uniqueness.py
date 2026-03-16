"""enforce task-scoped uniqueness for agent findings

Revision ID: 9a7b6c5d4e3f
Revises: 8c1d2e3f4a5b
Create Date: 2026-03-16 20:35:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "9a7b6c5d4e3f"
down_revision = "8c1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize blank identity/fingerprint to NULL before dedup/index build.
    op.execute(
        """
        UPDATE agent_findings
        SET finding_identity = NULL
        WHERE finding_identity IS NOT NULL
          AND btrim(finding_identity) = ''
        """
    )
    op.execute(
        """
        UPDATE agent_findings
        SET fingerprint = NULL
        WHERE fingerprint IS NOT NULL
          AND btrim(fingerprint) = ''
        """
    )

    # Deduplicate by task_id + finding_identity: keep the latest row.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY task_id, finding_identity
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM agent_findings
            WHERE finding_identity IS NOT NULL
        )
        DELETE FROM agent_findings af
        USING ranked r
        WHERE af.id = r.id
          AND r.rn > 1
        """
    )

    # Deduplicate by task_id + fingerprint: keep the latest row.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY task_id, fingerprint
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM agent_findings
            WHERE fingerprint IS NOT NULL
        )
        DELETE FROM agent_findings af
        USING ranked r
        WHERE af.id = r.id
          AND r.rn > 1
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_findings_task_finding_identity
        ON agent_findings (task_id, finding_identity)
        WHERE finding_identity IS NOT NULL AND btrim(finding_identity) <> ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_findings_task_fingerprint
        ON agent_findings (task_id, fingerprint)
        WHERE fingerprint IS NOT NULL AND btrim(fingerprint) <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_agent_findings_task_fingerprint")
    op.execute("DROP INDEX IF EXISTS ux_agent_findings_task_finding_identity")
