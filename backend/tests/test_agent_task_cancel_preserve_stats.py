from types import SimpleNamespace

from app.api.v1.endpoints.agent_tasks import _snapshot_runtime_stats_to_task
from app.models.agent_task import AgentTask
import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401


class _StubAgent:
    def __init__(self, iterations: int, tool_calls: int, tokens_used: int) -> None:
        self._stats = {
            "iterations": iterations,
            "tool_calls": tool_calls,
            "tokens_used": tokens_used,
        }

    def get_stats(self):
        return dict(self._stats)


def test_snapshot_runtime_stats_to_task_preserves_runtime_values():
    task = AgentTask(
        id="task-1",
        project_id="project-1",
        created_by="user-1",
        total_iterations=0,
        tool_calls_count=0,
        tokens_used=0,
    )
    orchestrator = SimpleNamespace(
        get_stats=lambda: {"iterations": 5, "tool_calls": 7, "tokens_used": 90},
        sub_agents={
            "recon": _StubAgent(2, 3, 20),
            "analysis": _StubAgent(4, 5, 40),
        },
    )

    snapshot = _snapshot_runtime_stats_to_task(task, orchestrator)

    assert snapshot == {"iterations": 11, "tool_calls": 15, "tokens_used": 150}
    assert task.total_iterations == 11
    assert task.tool_calls_count == 15
    assert task.tokens_used == 150


def test_snapshot_runtime_stats_to_task_uses_max_not_overwrite():
    task = AgentTask(
        id="task-2",
        project_id="project-1",
        created_by="user-1",
        total_iterations=30,
        tool_calls_count=40,
        tokens_used=500,
    )
    orchestrator = SimpleNamespace(
        get_stats=lambda: {"iterations": 1, "tool_calls": 2, "tokens_used": 3},
        sub_agents={},
    )

    _snapshot_runtime_stats_to_task(task, orchestrator)

    assert task.total_iterations == 30
    assert task.tool_calls_count == 40
    assert task.tokens_used == 500
