"""add yasa rule configs and task binding

Revision ID: c9d0e1f2a3b4
Revises: b9d8e7f6a5b4
Create Date: 2026-03-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS yasa_rule_configs (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            language VARCHAR NOT NULL,
            checker_pack_ids TEXT,
            checker_ids TEXT NOT NULL,
            rule_config_json TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            source VARCHAR NOT NULL DEFAULT 'custom',
            created_by VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_rule_configs_created_at
        ON yasa_rule_configs (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_rule_configs_language_active
        ON yasa_rule_configs (language, is_active)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_yasa_rule_configs_source_active
        ON yasa_rule_configs (source, is_active)
        """
    )

    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        ADD COLUMN IF NOT EXISTS rule_config_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        ADD COLUMN IF NOT EXISTS rule_config_name VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        ADD COLUMN IF NOT EXISTS rule_config_source VARCHAR
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_yasa_scan_tasks_rule_config_id'
            ) THEN
                ALTER TABLE yasa_scan_tasks
                ADD CONSTRAINT fk_yasa_scan_tasks_rule_config_id
                FOREIGN KEY (rule_config_id) REFERENCES yasa_rule_configs(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE yasa_scan_tasks DROP CONSTRAINT IF EXISTS fk_yasa_scan_tasks_rule_config_id")
    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        DROP COLUMN IF EXISTS rule_config_source
        """
    )
    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        DROP COLUMN IF EXISTS rule_config_name
        """
    )
    op.execute(
        """
        ALTER TABLE yasa_scan_tasks
        DROP COLUMN IF EXISTS rule_config_id
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_yasa_rule_configs_source_active")
    op.execute("DROP INDEX IF EXISTS ix_yasa_rule_configs_language_active")
    op.execute("DROP INDEX IF EXISTS ix_yasa_rule_configs_created_at")
    op.execute("DROP TABLE IF EXISTS yasa_rule_configs")
