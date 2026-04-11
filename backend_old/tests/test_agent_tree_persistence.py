from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1.endpoints.agent_tasks_runtime import _save_agent_tree
from app.services.agent.core import agent_registry


@pytest.mark.asyncio
async def test_save_agent_tree_persists_only_current_task_nodes():
    db = SimpleNamespace(
        execute=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )

    agent_registry.clear()
    try:
        agent_registry.register_agent(
            agent_id="agent-root-1",
            agent_name="Orchestrator",
            agent_type="orchestrator",
            task="root task 1",
            task_id="task-1",
        )
        agent_registry.register_agent(
            agent_id="agent-child-1",
            agent_name="Recon",
            agent_type="recon",
            task="child task 1",
            parent_id="agent-root-1",
        )
        agent_registry.register_agent(
            agent_id="agent-root-2",
            agent_name="Orchestrator",
            agent_type="orchestrator",
            task="root task 2",
            task_id="task-2",
        )

        await _save_agent_tree(db, "task-1")

        saved_agent_ids = [call.args[0].agent_id for call in db.add.call_args_list]
        assert saved_agent_ids == ["agent-root-1", "agent-child-1"]
        assert db.execute.await_count == 1
        db.commit.assert_awaited_once()
        db.rollback.assert_not_called()
    finally:
        agent_registry.clear()
