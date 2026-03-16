"""legacy compatibility bridge for agent findings report revision

Revision ID: c4b1a7e8d9f0
Revises:
Create Date: 2026-03-15 12:10:00.000000

"""

# revision identifiers, used by Alembic.
revision = "c4b1a7e8d9f0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Compatibility no-op.

    This revision existed before the Alembic history squash. Some deployed
    databases still have alembic_version=c4b1a7e8d9f0, so we keep a stub here
    to let Alembic resolve that legacy state and continue upgrading through the
    squashed history.
    """


def downgrade() -> None:
    pass
