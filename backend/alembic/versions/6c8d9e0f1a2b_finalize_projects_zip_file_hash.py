"""finalize projects zip_file_hash bridge

Revision ID: 6c8d9e0f1a2b
Revises: 5b0f3c9a6d7e
Create Date: 2026-03-13 21:20:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "6c8d9e0f1a2b"
down_revision = "5b0f3c9a6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS zip_file_hash VARCHAR(64)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_zip_file_hash
        ON projects (zip_file_hash)
        """
    )


def downgrade() -> None:
    pass
