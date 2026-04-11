"""add phpstan rule soft delete flag

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-16 16:20:00.000000

变更目的：为 PHPStan 规则页支持可恢复删除，新增 is_deleted 状态字段。
回滚范围：仅移除 phpstan_rule_states.is_deleted 字段及相关索引。
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE phpstan_rule_states
        ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_phpstan_rule_states_is_deleted
        ON phpstan_rule_states (is_deleted)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_phpstan_rule_states_is_deleted")
    op.execute(
        """
        ALTER TABLE phpstan_rule_states
        DROP COLUMN IF EXISTS is_deleted
        """
    )
