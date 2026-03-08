import os
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import agent_tasks as agent_tasks_module


class _FakeSandboxManager:
    def __init__(self):
        self.is_available = True

    async def initialize(self):
        self.is_available = True


class _FakeEventManager:
    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory

    def create_queue(self, task_id: str):
        self.task_id = task_id


class _FakeEventEmitter:
    def __init__(self, task_id: str, event_manager):
        self.task_id = task_id
        self.event_manager = event_manager

    async def emit_phase_start(self, *args, **kwargs):
        return None

    async def emit_info(self, *args, **kwargs):
        return None

    async def emit_warning(self, *args, **kwargs):
        return None

    async def emit_error(self, *args, **kwargs):
        return None

    async def emit_task_error(self, *args, **kwargs):
        return None


class _FakeLLMService:
    def __init__(self, user_config=None):
        self.user_config = user_config
        self.config = {"provider": "test"}

    async def chat_completion_raw(self, *args, **kwargs):
        return {"content": "Hello", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


class _FakeSession:
    def __init__(self, task):
        self.task = task

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return self.task

    async def commit(self):
        return None


class _StopAfterMCPRuntime(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_execute_agent_task_normalizes_project_root_before_building_mcp_runtime(
    monkeypatch,
    tmp_path,
):
    import app.services.agent.event_manager as event_manager_module
    import app.services.agent.tools as tools_module
    import app.services.llm.service as llm_service_module

    raw_project_root = os.path.join(str(tmp_path), ".")
    expected_project_root = os.path.abspath(raw_project_root)
    project = SimpleNamespace(id="project-1", name="Demo Project")
    task = SimpleNamespace(
        project=project,
        status=None,
        started_at=None,
        current_phase=None,
        current_step=None,
        created_by="user-1",
        branch_name="main",
        target_files=None,
        verification_level=None,
        exclude_patterns=None,
        error_message=None,
        completed_at=None,
    )
    captured = {}

    monkeypatch.setattr(agent_tasks_module, "async_session_factory", lambda: _FakeSession(task))

    async def _fake_get_user_config(*args, **kwargs):
        return {"otherConfig": {}}

    async def _fake_get_project_root(*args, **kwargs):
        return raw_project_root

    async def _passthrough_run_with_retries(step_name, task_id, event_emitter, callback, **kwargs):
        del step_name, task_id, event_emitter, kwargs
        return await callback()

    async def _fake_initialize_tools(*args, **kwargs):
        return {}

    async def _fake_wait_for_terminal_tool_drain(*args, **kwargs):
        return {}

    def _fake_build_task_mcp_runtime(*, project_root, **kwargs):
        del kwargs
        captured["project_root"] = project_root
        raise _StopAfterMCPRuntime("stop after capturing runtime input")

    monkeypatch.setattr(agent_tasks_module, "_get_user_config", _fake_get_user_config)
    monkeypatch.setattr(agent_tasks_module, "_get_project_root", _fake_get_project_root)
    monkeypatch.setattr(agent_tasks_module, "_run_with_retries", _passthrough_run_with_retries)
    monkeypatch.setattr(agent_tasks_module, "_initialize_tools", _fake_initialize_tools)
    monkeypatch.setattr(agent_tasks_module, "_build_task_mcp_runtime", _fake_build_task_mcp_runtime)
    monkeypatch.setattr(agent_tasks_module, "_wait_for_terminal_tool_drain", _fake_wait_for_terminal_tool_drain)
    monkeypatch.setattr(agent_tasks_module, "_build_tool_drain_metadata", lambda result: dict(result or {}))

    async def _fake_save_agent_tree(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_tasks_module, "_save_agent_tree", _fake_save_agent_tree)
    monkeypatch.setattr(agent_tasks_module, "_snapshot_runtime_stats_to_task", lambda *args, **kwargs: {})
    monkeypatch.setattr(agent_tasks_module, "is_task_cancelled", lambda *args, **kwargs: False)

    monkeypatch.setattr(tools_module, "SandboxManager", _FakeSandboxManager)
    monkeypatch.setattr(event_manager_module, "EventManager", _FakeEventManager)
    monkeypatch.setattr(event_manager_module, "AgentEventEmitter", _FakeEventEmitter)
    monkeypatch.setattr(llm_service_module, "LLMService", _FakeLLMService)

    await agent_tasks_module._execute_agent_task("task-1")

    assert captured["project_root"] == expected_project_root
    assert os.path.isabs(captured["project_root"])

