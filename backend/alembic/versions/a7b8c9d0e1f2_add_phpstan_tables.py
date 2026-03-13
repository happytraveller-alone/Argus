"""add_phpstan_tables

变更目的：
- 新增 PHPStan 静态扫描任务表与发现表，支持独立的 /static-tasks/phpstan 接口链路。

回滚范围：
- downgrade 会删除 phpstan_findings 与 phpstan_scan_tasks 两张表及相关索引。

Revision ID: a7b8c9d0e1f2
Revises: f2a1c9d8e7b6
Create Date: 2026-03-13 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f2a1c9d8e7b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phpstan_scan_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("target_path", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("total_findings", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("scan_duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 与 opengrep/gitleaks/bandit 索引风格对齐：包含 created_at DESC 与 lower(status) 表达式索引。
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phpstan_tasks_project_created_at "
        "ON phpstan_scan_tasks (project_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phpstan_tasks_project_lower_status_created_at "
        "ON phpstan_scan_tasks (project_id, lower(status), created_at DESC)"
    )

    op.create_table(
        "phpstan_findings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scan_task_id", sa.String(), sa.ForeignKey("phpstan_scan_tasks.id"), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("identifier", sa.String(), nullable=True),
        sa.Column("tip", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_phpstan_findings_scan_task_status_created",
        "phpstan_findings",
        ["scan_task_id", "status", "created_at"],
    )
    op.create_index(
        "ix_phpstan_findings_scan_task_file_line",
        "phpstan_findings",
        ["scan_task_id", "file_path", "line"],
    )
    op.create_index(
        "ix_phpstan_findings_scan_task_identifier",
        "phpstan_findings",
        ["scan_task_id", "identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_phpstan_findings_scan_task_identifier", table_name="phpstan_findings")
    op.drop_index("ix_phpstan_findings_scan_task_file_line", table_name="phpstan_findings")
    op.drop_index("ix_phpstan_findings_scan_task_status_created", table_name="phpstan_findings")
    op.drop_table("phpstan_findings")

    op.execute("DROP INDEX IF EXISTS ix_phpstan_tasks_project_lower_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_phpstan_tasks_project_created_at")
    op.drop_table("phpstan_scan_tasks")
