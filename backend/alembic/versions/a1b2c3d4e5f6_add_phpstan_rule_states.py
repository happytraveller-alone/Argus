"""add phpstan rule states table for rules page

Revision ID: a1b2c3d4e5f6
Revises: 9d3e4f5a6b7c
Create Date: 2026-03-16 10:40:00.000000

变更目的：为 PHPStan 规则页提供启停状态持久化存储（不影响扫描执行路径）。
回滚范围：仅删除 phpstan_rule_states 表及其索引。
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "9d3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS phpstan_rule_states (
            id VARCHAR PRIMARY KEY,
            rule_id VARCHAR NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_phpstan_rule_states_rule_id
        ON phpstan_rule_states (rule_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_phpstan_rule_states_is_active
        ON phpstan_rule_states (is_active)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_phpstan_rule_states_is_active")
    op.execute("DROP INDEX IF EXISTS ix_phpstan_rule_states_rule_id")
    op.execute("DROP TABLE IF EXISTS phpstan_rule_states")
