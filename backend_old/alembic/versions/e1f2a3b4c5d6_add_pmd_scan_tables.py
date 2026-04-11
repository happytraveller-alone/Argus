"""add pmd scan tables

Revision ID: e1f2a3b4c5d6
Revises: da4e5f6a7b8c
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op


revision = "e1f2a3b4c5d6"
down_revision = "da4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pmd_scan_tasks (
            id VARCHAR PRIMARY KEY,
            project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            target_path VARCHAR NOT NULL,
            ruleset VARCHAR NOT NULL DEFAULT 'security',
            total_findings INTEGER NOT NULL DEFAULT 0,
            high_count INTEGER NOT NULL DEFAULT 0,
            medium_count INTEGER NOT NULL DEFAULT 0,
            low_count INTEGER NOT NULL DEFAULT 0,
            scan_duration_ms INTEGER NOT NULL DEFAULT 0,
            files_scanned INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_tasks_project_created_at
        ON pmd_scan_tasks (project_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_tasks_project_lower_status_created_at
        ON pmd_scan_tasks (project_id, lower(status), created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pmd_findings (
            id VARCHAR PRIMARY KEY,
            scan_task_id VARCHAR NOT NULL REFERENCES pmd_scan_tasks(id) ON DELETE CASCADE,
            file_path VARCHAR NOT NULL,
            begin_line INTEGER NULL,
            end_line INTEGER NULL,
            rule VARCHAR NULL,
            ruleset VARCHAR NULL,
            priority INTEGER NULL,
            message TEXT NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_findings_scan_task_status_created
        ON pmd_findings (scan_task_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_findings_scan_task_file_line
        ON pmd_findings (scan_task_id, file_path, begin_line)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_findings_scan_task_priority
        ON pmd_findings (scan_task_id, priority)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pmd_findings_scan_task_priority")
    op.execute("DROP INDEX IF EXISTS ix_pmd_findings_scan_task_file_line")
    op.execute("DROP INDEX IF EXISTS ix_pmd_findings_scan_task_status_created")
    op.execute("DROP TABLE IF EXISTS pmd_findings")
    op.execute("DROP INDEX IF EXISTS ix_pmd_tasks_project_lower_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_pmd_tasks_project_created_at")
    op.execute("DROP TABLE IF EXISTS pmd_scan_tasks")
