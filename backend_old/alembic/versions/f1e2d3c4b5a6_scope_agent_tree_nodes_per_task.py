"""scope agent tree node uniqueness to each task

Revision ID: f1e2d3c4b5a6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-03 00:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "f1e2d3c4b5a6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_tree_nodes_agent_id")
    op.create_index(
        "ix_agent_tree_nodes_agent_id",
        "agent_tree_nodes",
        ["agent_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_agent_tree_nodes_task_agent",
        "agent_tree_nodes",
        ["task_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_agent_tree_nodes_task_agent", "agent_tree_nodes", type_="unique")
    op.drop_index("ix_agent_tree_nodes_agent_id", table_name="agent_tree_nodes")
    op.create_index(
        "ix_agent_tree_nodes_agent_id",
        "agent_tree_nodes",
        ["agent_id"],
        unique=True,
    )
