from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import agent_tasks_runtime as runtime_module
from app.models.agent_task import AgentTaskStatus


class _FakeDB:
    def __init__(self, tracker):
        self.tracker = tracker

    async def commit(self):
        self.tracker.append(("commit", None))


class _FakeEmitter:
    def __init__(self, tracker):
        self.tracker = tracker

    async def emit_task_complete(self, *args, **kwargs):
        self.tracker.append(("task_complete", kwargs))

    async def emit_task_error(self, *args, **kwargs):
        self.tracker.append(("task_error", kwargs))

    async def emit_error(self, *args, **kwargs):
        self.tracker.append(("error", kwargs))

    async def emit_task_cancelled(self, *args, **kwargs):
        self.tracker.append(("task_cancel", kwargs))


def _make_task():
    return SimpleNamespace(
        status=AgentTaskStatus.RUNNING,
        completed_at=None,
        error_message=None,
        current_phase="reporting",
    )


@pytest.mark.asyncio
async def test_finalize_terminal_state_commits_completed_only_after_tool_drain(monkeypatch):
    tracker = []
    task = _make_task()

    async def _fake_wait_for_terminal_tool_drain(**kwargs):
        del kwargs
        tracker.append(("drain", task.status))
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 12,
            "pending_tool_calls": [],
        }

    monkeypatch.setattr(
        agent_tasks_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )
    monkeypatch.setattr(
        runtime_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )

    await agent_tasks_module._finalize_task_terminal_state(
        db=_FakeDB(tracker),
        task=task,
        task_id="task-1",
        event_emitter=_FakeEmitter(tracker),
        event_manager=object(),
        desired_status=AgentTaskStatus.COMPLETED,
        success_payload={
            "findings_count": 2,
            "duration_ms": 1500,
            "message": "done",
            "extra_metadata": {"source": "test"},
        },
    )

    assert tracker[0] == ("drain", AgentTaskStatus.RUNNING)
    assert tracker[1][0] == "commit"
    assert tracker[2][0] == "task_complete"
    assert task.status == AgentTaskStatus.COMPLETED
    assert task.error_message is None


@pytest.mark.asyncio
async def test_finalize_terminal_state_fails_when_tool_drain_times_out(monkeypatch):
    tracker = []
    task = _make_task()

    async def _fake_wait_for_terminal_tool_drain(**kwargs):
        del kwargs
        return {
            "ready": False,
            "timed_out": True,
            "elapsed_ms": 180000,
            "pending_tool_calls": [{"tool_name": "read_file"}],
        }

    monkeypatch.setattr(
        agent_tasks_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )
    monkeypatch.setattr(
        runtime_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )

    result = await agent_tasks_module._finalize_task_terminal_state(
        db=_FakeDB(tracker),
        task=task,
        task_id="task-2",
        event_emitter=_FakeEmitter(tracker),
        event_manager=object(),
        desired_status=AgentTaskStatus.COMPLETED,
        success_payload={
            "findings_count": 1,
            "duration_ms": 1000,
        },
    )

    assert result["status"] == AgentTaskStatus.FAILED
    assert task.status == AgentTaskStatus.FAILED
    assert "终态收敛超时" in str(task.error_message)
    assert [name for name, _ in tracker] == ["commit", "task_error", "error"]


@pytest.mark.asyncio
async def test_finalize_terminal_state_fails_when_verification_gate_is_triggered(monkeypatch):
    tracker = []
    task = _make_task()

    async def _fake_wait_for_terminal_tool_drain(**kwargs):
        del kwargs
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 20,
            "pending_tool_calls": [],
        }

    monkeypatch.setattr(
        agent_tasks_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )
    monkeypatch.setattr(
        runtime_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )

    result = await agent_tasks_module._finalize_task_terminal_state(
        db=_FakeDB(tracker),
        task=task,
        task_id="task-3",
        event_emitter=_FakeEmitter(tracker),
        event_manager=object(),
        desired_status=AgentTaskStatus.COMPLETED,
        success_payload={
            "findings_count": 1,
            "duration_ms": 1000,
        },
        verification_gate_message="verification_pending_gate: pending=1",
        verification_gate_metadata={"pending_count": 1},
    )

    assert result["status"] == AgentTaskStatus.FAILED
    assert task.status == AgentTaskStatus.FAILED
    assert task.error_message == "verification_pending_gate: pending=1"
    assert [name for name, _ in tracker] == ["commit", "task_error", "error"]


@pytest.mark.asyncio
async def test_finalize_terminal_state_emits_cancel_event_without_completion(monkeypatch):
    tracker = []
    task = _make_task()

    async def _fake_wait_for_terminal_tool_drain(**kwargs):
        del kwargs
        raise AssertionError("cancelled paths should skip tool drain")

    monkeypatch.setattr(
        agent_tasks_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )
    monkeypatch.setattr(
        runtime_module,
        "_wait_for_terminal_tool_drain",
        _fake_wait_for_terminal_tool_drain,
    )

    result = await agent_tasks_module._finalize_task_terminal_state(
        db=_FakeDB(tracker),
        task=task,
        task_id="task-4",
        event_emitter=_FakeEmitter(tracker),
        event_manager=object(),
        desired_status=AgentTaskStatus.CANCELLED,
        skip_drain_wait=True,
        cancel_message="任务已取消",
    )

    assert result["status"] == AgentTaskStatus.CANCELLED
    assert task.status == AgentTaskStatus.CANCELLED
    assert [name for name, _ in tracker] == ["commit", "task_cancel"]
