"""drop legacy audit tables

Revision ID: b9d8e7f6a5b4
Revises: a8f1c2d3e4b5
Create Date: 2026-03-21 10:30:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b9d8e7f6a5b4"
down_revision = "a8f1c2d3e4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_management_metrics
        DROP COLUMN IF EXISTS audit_tasks
        """
    )
    op.execute("DROP TABLE IF EXISTS audit_issues")
    op.execute("DROP TABLE IF EXISTS audit_tasks")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_management_metrics
        ADD COLUMN IF NOT EXISTS audit_tasks INTEGER DEFAULT 0
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_tasks (
            id VARCHAR PRIMARY KEY,
            project_id VARCHAR NOT NULL REFERENCES projects(id),
            created_by VARCHAR NOT NULL REFERENCES users(id),
            task_type VARCHAR NOT NULL,
            status VARCHAR,
            branch_name VARCHAR,
            exclude_patterns TEXT,
            scan_config TEXT,
            total_files INTEGER,
            scanned_files INTEGER,
            total_lines INTEGER,
            issues_count INTEGER,
            quality_score DOUBLE PRECISION,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_issues (
            id VARCHAR PRIMARY KEY,
            task_id VARCHAR NOT NULL REFERENCES audit_tasks(id),
            file_path VARCHAR NOT NULL,
            line_number INTEGER,
            column_number INTEGER,
            issue_type VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            title VARCHAR,
            message TEXT,
            description TEXT,
            suggestion TEXT,
            code_snippet TEXT,
            ai_explanation TEXT,
            status VARCHAR,
            resolved_by VARCHAR REFERENCES users(id),
            resolved_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_tasks_project_status_created_at
        ON audit_tasks (project_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_issues_task_status
        ON audit_issues (task_id, status)
        """
    )
