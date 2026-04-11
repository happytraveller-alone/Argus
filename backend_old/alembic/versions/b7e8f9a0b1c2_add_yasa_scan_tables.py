"""add yasa static scan tables

Revision ID: b7e8f9a0b1c2
Revises: e5f6a7b8c9d0
Create Date: 2026-03-16 18:25:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b7e8f9a0b1c2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS yasa_scan_tasks (
            id VARCHAR PRIMARY KEY,
            project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            target_path VARCHAR NOT NULL,
            language VARCHAR NOT NULL DEFAULT 'python',
            checker_pack_ids VARCHAR,
            checker_ids TEXT,
            rule_config_file VARCHAR,
            total_findings INTEGER NOT NULL DEFAULT 0,
            scan_duration_ms INTEGER NOT NULL DEFAULT 0,
            files_scanned INTEGER NOT NULL DEFAULT 0,
            diagnostics_summary TEXT,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_tasks_project_created_at
        ON yasa_scan_tasks (project_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_tasks_project_lower_status_created_at
        ON yasa_scan_tasks (project_id, lower(status), created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS yasa_findings (
            id VARCHAR PRIMARY KEY,
            scan_task_id VARCHAR NOT NULL REFERENCES yasa_scan_tasks(id) ON DELETE CASCADE,
            rule_id VARCHAR,
            rule_name VARCHAR,
            level VARCHAR NOT NULL DEFAULT 'warning',
            message TEXT NOT NULL,
            file_path VARCHAR NOT NULL,
            start_line INTEGER,
            end_line INTEGER,
            status VARCHAR NOT NULL DEFAULT 'open',
            raw_payload TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_findings_scan_task_status_created
        ON yasa_findings (scan_task_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_findings_scan_task_file_line
        ON yasa_findings (scan_task_id, file_path, start_line)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_findings_scan_task_level
        ON yasa_findings (scan_task_id, level)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_yasa_findings_scan_task_level")
    op.execute("DROP INDEX IF EXISTS ix_yasa_findings_scan_task_file_line")
    op.execute("DROP INDEX IF EXISTS ix_yasa_findings_scan_task_status_created")
    op.execute("DROP TABLE IF EXISTS yasa_findings")

    op.execute("DROP INDEX IF EXISTS ix_yasa_tasks_project_lower_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_yasa_tasks_project_created_at")
    op.execute("DROP TABLE IF EXISTS yasa_scan_tasks")
