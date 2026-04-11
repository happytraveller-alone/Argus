"""add pmd rule configs

Revision ID: da4e5f6a7b8c
Revises: d4e5f6a7b8c9
Create Date: 2026-03-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "da4e5f6a7b8c"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pmd_rule_configs (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            filename VARCHAR NOT NULL,
            xml_content TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_rule_configs_created_at
        ON pmd_rule_configs (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_rule_configs_is_active
        ON pmd_rule_configs (is_active)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pmd_rule_configs_is_active_created_at
        ON pmd_rule_configs (is_active, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pmd_rule_configs_is_active_created_at")
    op.execute("DROP INDEX IF EXISTS ix_pmd_rule_configs_is_active")
    op.execute("DROP INDEX IF EXISTS ix_pmd_rule_configs_created_at")
    op.execute("DROP TABLE IF EXISTS pmd_rule_configs")
