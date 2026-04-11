"""squashed baseline for current backend schema

Revision ID: 5b0f3c9a6d7e
Revises:
Create Date: 2026-03-13 20:45:00.000000

"""

from alembic import op

from app.db.schema_snapshots.baseline_5b0f3c9a6d7e import metadata as baseline_metadata


# revision identifiers, used by Alembic.
revision = "5b0f3c9a6d7e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    baseline_metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    baseline_metadata.drop_all(bind=bind, checkfirst=True)
