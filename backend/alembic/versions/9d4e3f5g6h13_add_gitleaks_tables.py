"""add_gitleaks_tables

Revision ID: 9d4e3f5g6h13
Revises: 8b2f3e2f4c12
Create Date: 2026-02-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d4e3f5g6h13'
down_revision = '8b2f3e2f4c12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 gitleaks_scan_tasks 表
    op.create_table(
        'gitleaks_scan_tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('target_path', sa.String(), nullable=False),
        sa.Column('no_git', sa.String(), nullable=False, server_default=sa.text("'true'")),
        sa.Column('total_findings', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('scan_duration_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('files_scanned', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 创建 gitleaks_findings 表
    op.create_table(
        'gitleaks_findings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('scan_task_id', sa.String(), sa.ForeignKey('gitleaks_scan_tasks.id'), nullable=False),
        sa.Column('rule_id', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('start_line', sa.Integer(), nullable=True),
        sa.Column('end_line', sa.Integer(), nullable=True),
        sa.Column('secret', sa.Text(), nullable=True),
        sa.Column('match', sa.Text(), nullable=True),
        sa.Column('commit', sa.String(), nullable=True),
        sa.Column('author', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('date', sa.String(), nullable=True),
        sa.Column('fingerprint', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default=sa.text("'open'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('gitleaks_findings')
    op.drop_table('gitleaks_scan_tasks')
