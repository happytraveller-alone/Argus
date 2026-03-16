"""Merge concurrent Alembic heads for phpstan rules and agent findings.

This revision only merges branches and does not change schema objects.
Downgrade will split the migration graph back into the two original heads.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = (
    "9a7b6c5d4e3f",
    "c3d4e5f6a7b8",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge revision: no-op.
    op.execute("SELECT 1")


def downgrade() -> None:
    # Split merged heads: no-op.
    op.execute("SELECT 1")
