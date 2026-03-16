"""squashed baseline for current backend schema

Revision ID: 5b0f3c9a6d7e
Revises:
Create Date: 2026-03-13 20:45:00.000000

"""

from alembic import op

from app.db.base import Base
from app.models import *  # noqa: F401,F403
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask  # noqa: F401


# revision identifiers, used by Alembic.
revision = "5b0f3c9a6d7e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
