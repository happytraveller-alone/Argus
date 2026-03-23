from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import agent_tasks_routes_results
from app.api.v1.endpoints.agent_tasks_routes_results import get_agent_tree
from app.models.agent_task import AgentTask
from app.models.project import Project


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_agent_tree_includes_verified_counts_and_preserves_legacy_totals():
    task_id = "task-1"
    now = datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc)
    root_node = SimpleNamespace(
        id="node-root",
        agent_id="root-agent",
        agent_name="Orchestrator",
        agent_type="orchestrator",
        parent_agent_id=None,
        depth=0,
        task_description="root task",
        knowledge_modules=[],
        status="completed",
        result_summary=None,
        findings_count=99,
        iterations=2,
        tokens_used=100,
        tool_calls=3,
        duration_ms=1000,
        created_at=now,
    )
    child_node = SimpleNamespace(
        id="node-child",
        agent_id="child-agent",
        agent_name="Verifier",
        agent_type="worker",
        parent_agent_id="root-agent",
        depth=1,
        task_description="child task",
        knowledge_modules=[],
        status="completed",
        result_summary=None,
        findings_count=5,
        iterations=1,
        tokens_used=50,
        tool_calls=1,
        duration_ms=500,
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(
                id=task_id,
                project_id="project-1",
                findings_count=12,
                verified_count=4,
            )
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([root_node, child_node]))

    result = await get_agent_tree(
        task_id=task_id,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.total_findings == 12
    assert result.verified_total_findings == 4
    assert len(result.nodes) == 2
    assert result.nodes[0].findings_count == 12
    assert result.nodes[0].verified_findings_count == 4
    assert result.nodes[1].findings_count == 5
    assert result.nodes[1].verified_findings_count == 0


@pytest.mark.asyncio
async def test_get_agent_tree_uses_live_verified_counts_while_task_running(monkeypatch):
    task_id = "task-running"
    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(
                id=task_id,
                project_id="project-1",
                findings_count=8,
                verified_count=0,
            )
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)

    monkeypatch.setattr(
        agent_tasks_routes_results,
        "_running_tasks",
        {task_id: SimpleNamespace()},
    )

    from app.services.agent.core import agent_registry

    tree = {
        "root_agent_id": "root-agent",
        "nodes": {
            "root-agent": {
                "id": "node-root",
                "name": "Orchestrator",
                "type": "orchestrator",
                "parent_id": None,
                "task": "root task",
                "knowledge_modules": [],
                "status": "running",
                "result": {
                    "findings": [
                        {"id": "f-1", "status": "verified"},
                        {"id": "f-2", "status": "verified", "is_verified": False},
                        {"id": "f-3", "status": "pending"},
                    ]
                },
            },
            "child-agent": {
                "id": "node-child",
                "name": "Verifier",
                "type": "verification",
                "parent_id": "root-agent",
                "task": "child task",
                "knowledge_modules": [],
                "status": "running",
                "result": {
                    "findings": [
                        {"id": "f-1", "status": "verified"},
                        {"id": "f-4", "status": "false_positive"},
                    ]
                },
            },
        },
    }

    monkeypatch.setattr(agent_registry, "get_agent_tree", lambda: tree)
    monkeypatch.setattr(
        agent_registry,
        "get_statistics",
        lambda: {"total": 2, "running": 2, "completed": 0, "failed": 0},
    )
    monkeypatch.setattr(agent_registry, "get_agent", lambda _agent_id: None)

    result = await get_agent_tree(
        task_id=task_id,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.total_findings == 8
    assert result.verified_total_findings == 2
    assert result.nodes[0].verified_findings_count == 2
