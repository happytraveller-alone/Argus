"""Add confidence, description, cwe fields to opengrep_rules

Revision ID: add_confidence_description_cwe
Revises: 1d99cd010134
Create Date: 2025-02-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_confidence_description_cwe'
down_revision = '1d99cd010134'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add confidence column
    op.add_column('opengrep_rules', sa.Column('confidence', sa.String(), nullable=True))
    
    # Add description column
    op.add_column('opengrep_rules', sa.Column('description', sa.Text(), nullable=True))
    
    # Add cwe column
    op.add_column('opengrep_rules', sa.Column('cwe', postgresql.JSON(), nullable=True))


def downgrade() -> None:
    # Drop columns in reverse order
    op.drop_column('opengrep_rules', 'cwe')
    op.drop_column('opengrep_rules', 'description')
    op.drop_column('opengrep_rules', 'confidence')
