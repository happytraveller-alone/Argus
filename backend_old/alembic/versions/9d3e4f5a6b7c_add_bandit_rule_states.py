"""add bandit rule states table for rules page

Revision ID: 9d3e4f5a6b7c
Revises: 9a7b6c5d4e3f
Create Date: 2026-03-15 19:10:00.000000

变更目的：为 Bandit 规则页提供启停状态持久化存储（不影响扫描执行路径）。
回滚范围：仅删除 bandit_rule_states 表及其索引。
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "9d3e4f5a6b7c"
down_revision = "9a7b6c5d4e3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bandit_rule_states (
            id VARCHAR PRIMARY KEY,
            test_id VARCHAR NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_bandit_rule_states_test_id
        ON bandit_rule_states (test_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_bandit_rule_states_is_active
        ON bandit_rule_states (is_active)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bandit_rule_states_is_active")
    op.execute("DROP INDEX IF EXISTS ix_bandit_rule_states_test_id")
    op.execute("DROP TABLE IF EXISTS bandit_rule_states")
