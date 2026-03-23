"""remove fixed static finding status

Revision ID: f6a7b8c9d0e1
Revises: b9d8e7f6a5b4
Create Date: 2026-03-21 22:50:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "b9d8e7f6a5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in (
        "gitleaks_findings",
        "bandit_findings",
        "phpstan_findings",
        "yasa_findings",
    ):
        op.execute(
            f"""
            UPDATE {table_name}
            SET status = 'verified'
            WHERE lower(status) = 'fixed'
            """
        )


def downgrade() -> None:
    # Irreversible data migration: historical "fixed" rows are folded into "verified".
    pass
