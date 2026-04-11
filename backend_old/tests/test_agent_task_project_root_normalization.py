import os
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import agent_tasks_execution as execution_module
from app.api.v1.endpoints import agent_tasks_runtime as runtime_module
from app.api.v1.endpoints import agent_tasks_tool_runtime as tool_runtime_module


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


class _StopAfterWriteScopeGuard(RuntimeError):
    pass


class _StopAfterGuardInjection(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_execute_agent_task_normalizes_project_root_before_building_write_scope_guard(
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

    monkeypatch.setattr(execution_module, "async_session_factory", lambda: _FakeSession(task))

    async def _fake_get_user_config(*args, **kwargs):
        return {"otherConfig": {}}

    async def _fake_run_task_llm_connection_test(*args, **kwargs):
        del args, kwargs
        return {"elapsed_ms": 1}

    async def _fake_get_project_root(*args, **kwargs):
        return raw_project_root

    async def _passthrough_run_with_retries(step_name, task_id, event_emitter, callback, **kwargs):
        del step_name, task_id, event_emitter, kwargs
        return await callback()

    async def _fake_initialize_tools(*args, **kwargs):
        return {}

    async def _fake_wait_for_terminal_tool_drain(*args, **kwargs):
        return {}

    def _fake_build_task_write_scope_guard(*, project_root, **kwargs):
        del kwargs
        captured["project_root"] = project_root
        raise _StopAfterWriteScopeGuard("stop after capturing runtime input")

    monkeypatch.setattr(execution_module, "_get_user_config", _fake_get_user_config)
    monkeypatch.setattr(execution_module, "_get_project_root", _fake_get_project_root)
    monkeypatch.setattr(execution_module, "_run_with_retries", _passthrough_run_with_retries)
    monkeypatch.setattr(execution_module, "_initialize_tools", _fake_initialize_tools)
    monkeypatch.setattr(tool_runtime_module, "build_task_write_scope_guard", _fake_build_task_write_scope_guard)
    monkeypatch.setattr(execution_module, "build_task_write_scope_guard", _fake_build_task_write_scope_guard)
    monkeypatch.setattr(tool_runtime_module, "_run_task_llm_connection_test", _fake_run_task_llm_connection_test)
    monkeypatch.setattr(execution_module, "_run_task_llm_connection_test", _fake_run_task_llm_connection_test)
    monkeypatch.setattr(runtime_module, "_wait_for_terminal_tool_drain", _fake_wait_for_terminal_tool_drain)
    monkeypatch.setattr(execution_module, "_wait_for_terminal_tool_drain", _fake_wait_for_terminal_tool_drain)
    monkeypatch.setattr(runtime_module, "_build_tool_drain_metadata", lambda result: dict(result or {}))

    async def _fake_save_agent_tree(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime_module, "_save_agent_tree", _fake_save_agent_tree)
    monkeypatch.setattr(execution_module, "_save_agent_tree", _fake_save_agent_tree)
    monkeypatch.setattr(runtime_module, "_snapshot_runtime_stats_to_task", lambda *args, **kwargs: {})
    monkeypatch.setattr(execution_module, "_snapshot_runtime_stats_to_task", lambda *args, **kwargs: {})
    monkeypatch.setattr(runtime_module, "is_task_cancelled", lambda *args, **kwargs: False)
    monkeypatch.setattr(execution_module, "is_task_cancelled", lambda *args, **kwargs: False)

    monkeypatch.setattr(tools_module, "SandboxManager", _FakeSandboxManager)
    monkeypatch.setattr(event_manager_module, "EventManager", _FakeEventManager)
    monkeypatch.setattr(event_manager_module, "AgentEventEmitter", _FakeEventEmitter)
    monkeypatch.setattr(llm_service_module, "LLMService", _FakeLLMService)

    await agent_tasks_module._execute_agent_task("task-1")

    assert captured["project_root"] == expected_project_root
    assert os.path.isabs(captured["project_root"])


@pytest.mark.asyncio
async def test_execute_agent_task_injects_write_scope_guard_into_agents_and_orchestrator(
    monkeypatch,
    tmp_path,
):
    import app.services.agent.agents as agents_module
    import app.services.agent.event_manager as event_manager_module
    import app.services.agent.tools as tools_module
    import app.services.agent.workflow as workflow_module
    import app.services.agent.workflow.models as workflow_models_module
    import app.services.llm.service as llm_service_module

    project_root = os.path.abspath(str(tmp_path))
    project = SimpleNamespace(id="project-1", name="Demo Project", programming_languages=[])
    task = SimpleNamespace(
        project=project,
        status=None,
        started_at=None,
        current_phase=None,
        current_step=None,
        created_by="user-1",
        branch_name="main",
        target_files=["src/demo.py"],
        target_vulnerabilities=[],
        verification_level=None,
        exclude_patterns=None,
        error_message=None,
        completed_at=None,
        name="demo",
        description="demo",
        max_iterations=None,
        agent_config={},
    )

    class _FakeAgent:
        instances = []

        def __init__(self, *args, **kwargs):
            del args, kwargs
            self.config = SimpleNamespace(metadata={})
            self.guard = None
            _FakeAgent.instances.append(self)

        def set_cancel_callback(self, callback):
            self.cancel_callback = callback

        def set_write_scope_guard(self, guard):
            self.guard = guard

    class _FakeWorkflowOrchestrator(_FakeAgent):
        instance = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            _FakeWorkflowOrchestrator.instance = self

        def _register_to_registry(self, task=None):
            self.registry_task = task

    async def _fake_get_user_config(*args, **kwargs):
        return {"otherConfig": {}}

    async def _fake_run_task_llm_connection_test(*args, **kwargs):
        del args, kwargs
        return {"elapsed_ms": 1}

    async def _fake_get_project_root(*args, **kwargs):
        return project_root

    async def _passthrough_run_with_retries(step_name, task_id, event_emitter, callback, **kwargs):
        del step_name, task_id, event_emitter, kwargs
        return await callback()

    async def _fake_initialize_tools(*args, **kwargs):
        return {
            "recon": {},
            "analysis": {},
            "verification": {},
            "report": {},
            "business_logic_recon": {},
            "business_logic_analysis": {},
            "orchestrator": {},
        }

    def _fake_collect_project_info(*args, **kwargs):
        del args, kwargs
        guards = [agent.guard for agent in _FakeAgent.instances]
        assert guards, "expected fake agents to be created"
        assert all(guard is not None for guard in guards)
        raise _StopAfterGuardInjection("stop after guard injection")

    monkeypatch.setattr(execution_module, "async_session_factory", lambda: _FakeSession(task))
    monkeypatch.setattr(execution_module, "_get_user_config", _fake_get_user_config)
    monkeypatch.setattr(execution_module, "_get_project_root", _fake_get_project_root)
    monkeypatch.setattr(execution_module, "_run_with_retries", _passthrough_run_with_retries)
    monkeypatch.setattr(execution_module, "_initialize_tools", _fake_initialize_tools)
    monkeypatch.setattr(execution_module, "_collect_project_info", _fake_collect_project_info)
    monkeypatch.setattr(tool_runtime_module, "_run_task_llm_connection_test", _fake_run_task_llm_connection_test)
    monkeypatch.setattr(execution_module, "_run_task_llm_connection_test", _fake_run_task_llm_connection_test)

    async def _fake_wait_for_terminal_tool_drain(*args, **kwargs):
        del args, kwargs
        return {}

    async def _fake_save_agent_tree(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime_module, "_wait_for_terminal_tool_drain", _fake_wait_for_terminal_tool_drain)
    monkeypatch.setattr(execution_module, "_wait_for_terminal_tool_drain", _fake_wait_for_terminal_tool_drain)
    monkeypatch.setattr(runtime_module, "_build_tool_drain_metadata", lambda result: dict(result or {}))
    monkeypatch.setattr(runtime_module, "_save_agent_tree", _fake_save_agent_tree)
    monkeypatch.setattr(execution_module, "_save_agent_tree", _fake_save_agent_tree)
    monkeypatch.setattr(runtime_module, "_snapshot_runtime_stats_to_task", lambda *args, **kwargs: {})
    monkeypatch.setattr(execution_module, "_snapshot_runtime_stats_to_task", lambda *args, **kwargs: {})
    monkeypatch.setattr(runtime_module, "is_task_cancelled", lambda *args, **kwargs: False)
    monkeypatch.setattr(execution_module, "is_task_cancelled", lambda *args, **kwargs: False)

    monkeypatch.setattr(tools_module, "SandboxManager", _FakeSandboxManager)
    monkeypatch.setattr(event_manager_module, "EventManager", _FakeEventManager)
    monkeypatch.setattr(event_manager_module, "AgentEventEmitter", _FakeEventEmitter)
    monkeypatch.setattr(llm_service_module, "LLMService", _FakeLLMService)

    monkeypatch.setattr(agents_module, "ReconAgent", _FakeAgent)
    monkeypatch.setattr(agents_module, "AnalysisAgent", _FakeAgent)
    monkeypatch.setattr(agents_module, "VerificationAgent", _FakeAgent)
    monkeypatch.setattr(agents_module, "ReportAgent", _FakeAgent)
    monkeypatch.setattr(agents_module, "BusinessLogicReconAgent", _FakeAgent)
    monkeypatch.setattr(agents_module, "BusinessLogicAnalysisAgent", _FakeAgent)
    monkeypatch.setattr(workflow_module, "WorkflowOrchestratorAgent", _FakeWorkflowOrchestrator)
    monkeypatch.setattr(workflow_models_module, "WorkflowConfig", lambda **kwargs: SimpleNamespace(**kwargs))

    await agent_tasks_module._execute_agent_task("task-1")

    guards = [agent.guard for agent in _FakeAgent.instances]
    assert len(guards) >= 7
    assert all(guard is not None for guard in guards)
    assert _FakeWorkflowOrchestrator.instance is not None
    assert _FakeWorkflowOrchestrator.instance.guard is not None


@pytest.mark.asyncio
async def test_get_project_root_rejects_non_zip_projects(monkeypatch):
    project = SimpleNamespace(
        id="project-repo",
        source_type="repository",
        repository_url="https://github.com/org/repo.git",
        repository_type="github",
        default_branch="main",
    )

    monkeypatch.setattr(runtime_module, "is_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(execution_module, "is_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(execution_module.os, "makedirs", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError) as exc_info:
        await agent_tasks_module._get_project_root(
            project,
            task_id="task-repo",
        )

    assert str(exc_info.value) == "仅支持 ZIP 项目"
