import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime
from app.core.config import settings
from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import (
    FastMCPHttpAdapter,
    FastMCPStdioAdapter,
    MCPRuntime,
    QmdLazyIndexAdapter,
    TaskWriteScopeGuard,
)


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _ReadSchema(BaseModel):
    file_path: str


class _LocalReadTool:
    args_schema = _ReadSchema
    name = "read_file"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(
            success=True,
            data=f"local-read:{kwargs.get('file_path')}",
            error=None,
            metadata={"file_path": kwargs.get("file_path")},
        )


class _WriteSchema(BaseModel):
    file_path: str


class _LocalWriteTool:
    args_schema = _WriteSchema
    name = "edit_file"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=True, data="local-write", error=None, metadata={})


class _SuccessFilesystemAdapter:
    async def call_tool(self, tool_name, arguments):
        return {
            "success": True,
            "data": f"mcp:{tool_name}:{arguments.get('path')}",
            "metadata": {"adapter": "filesystem"},
        }


class _SuccessCodeIndexAdapter:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == "get_file_summary"
        assert arguments.get("path") == "src/time64.c"
        return {
            "success": True,
            "data": {
                "symbols": [
                    {
                        "name": "asctime64_r",
                        "kind": "function",
                        "start_line": 120,
                        "end_line": 240,
                    }
                ]
            },
            "metadata": {"adapter": "code_index"},
        }


class _SuccessFilesystemSearchAdapter:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == "search_files"
        assert arguments.get("pattern") == "dangerous_call"
        return {
            "success": True,
            "data": "src/app.py:88: dangerous_call()",
            "metadata": {"adapter": "filesystem"},
        }


class _SuccessCodeIndexSearchAdapter:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == "search_code_advanced"
        assert arguments.get("pattern") == "dangerous_call"
        return {
            "success": True,
            "data": "src/app.py:88: dangerous_call()",
            "metadata": {"adapter": "code_index"},
        }


class _SuccessCodeIndexListAdapter:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == "find_files"
        return {
            "success": True,
            "data": {"files": ["src/main.py", "src/utils.py"]},
            "metadata": {"adapter": "code_index"},
        }


class _CaptureFilesystemAdapter:
    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        return {
            "success": True,
            "data": "filesystem-ok",
            "metadata": {"adapter": "filesystem"},
        }


class _CaptureCodeIndexAdapter:
    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        return {
            "success": True,
            "data": "code-index-ok",
            "metadata": {"adapter": "code_index"},
        }


class _FlakyReadTool:
    args_schema = _ReadSchema
    name = "read_file"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        if self.execute_calls < 2:
            return SimpleNamespace(
                success=False,
                data="",
                error="transient network timeout",
                metadata={},
            )
        return SimpleNamespace(
            success=True,
            data="recovered-content",
            error=None,
            metadata={},
        )


def _make_agent(*, tools, runtime, metadata=None):
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(
            name="test-agent",
            agent_type=AgentType.ANALYSIS,
            metadata=metadata or {},
        ),
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    agent.set_mcp_runtime(runtime)
    return agent, emitter


def _events_by_type(emitter, event_type: str):
    events = []
    for call in emitter.emit.await_args_list:
        event_data = call.args[0]
        if event_data.event_type == event_type:
            events.append(event_data)
    return events


@pytest.mark.asyncio
async def test_write_tools_route_to_mcp_and_emit_scope_metadata(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": _SuccessFilesystemAdapter()},
        write_scope_guard=guard,
    )
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool(
        "edit_file",
        {
            "file_path": "src/fix.py",
            "old_text": "a",
            "new_text": "b",
            "reason": "verification fix",
            "finding_id": "f-1",
        },
    )

    assert "mcp:edit_file:src/fix.py" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) >= 1
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("write_scope_allowed") is True
    assert metadata.get("write_scope_file") == "src/fix.py"


@pytest.mark.asyncio
async def test_mcp_fallback_still_cannot_bypass_write_scope(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
    )
    local_write_tool = _LocalWriteTool()
    agent, _ = _make_agent(tools={"edit_file": local_write_tool}, runtime=runtime)

    output = await agent.execute_tool(
        "edit_file",
        {
            "file_path": "src/unsafe.py",
            "old_text": "a",
            "new_text": "b",
        },
    )

    assert "写入策略校验失败" in output
    assert local_write_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_mcp_failure_for_read_file_is_fail_closed_when_mcp_only_enforced(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
    )
    local_read_tool = _LocalReadTool()
    agent, emitter = _make_agent(
        tools={"read_file": local_read_tool},
        runtime=runtime,
        metadata={"mcp_only_enforced": True},
    )

    output = await agent.execute_tool("read_file", {"file_path": "src/sql_vuln.py"})

    assert "MCP 严格模式阻断" in output
    assert local_read_tool.execute_calls == 0
    tool_result_events = _events_by_type(emitter, "tool_result")
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_only_enforced") is True


@pytest.mark.asyncio
async def test_mcp_strict_mode_blocks_local_fallback_for_read_file(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
        strict_mode=True,
    )
    local_read_tool = _LocalReadTool()
    agent, _ = _make_agent(tools={"read_file": local_read_tool}, runtime=runtime)

    output = await agent.execute_tool("read_file", {"file_path": "src/sql_vuln.py"})

    assert "MCP 严格模式阻断" in output
    assert local_read_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_mcp_local_proxy_route_keeps_mcp_metadata(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
    )
    local_read_tool = _LocalReadTool()
    assert runtime.register_local_tool("local_read_file", local_read_tool) is True
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool("local_read_file", {"file_path": "src/sql_vuln.py"})

    assert "local-read:src/sql_vuln.py" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("mcp_adapter") == "local_proxy"


@pytest.mark.asyncio
async def test_mcp_strict_mode_blocks_verify_reachability_without_mcp_routes(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
        strict_mode=True,
    )
    local_read_tool = _LocalReadTool()
    agent, _ = _make_agent(tools={"read_file": local_read_tool}, runtime=runtime)

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/sql_vuln.py", "line_start": 12},
    )

    assert "verify_reachability 执行错误" in output
    assert "blocked_reason: mcp_unavailable" in output
    assert local_read_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_locate_enclosing_function_routes_to_code_index(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"code_index": _SuccessCodeIndexAdapter()},
        write_scope_guard=guard,
    )
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool(
        "locate_enclosing_function",
        {"file_path": "src/time64.c", "line_start": 168},
    )

    assert "asctime64_r" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) >= 1
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("mcp_tool") == "get_file_summary"
    assert metadata.get("alias_used") == "locate_enclosing_function"
    tool_call_events = _events_by_type(emitter, "tool_call")
    call_metadata = tool_call_events[-1].metadata or {}
    assert call_metadata.get("mcp_adapter") == "code_index"
    assert call_metadata.get("mcp_tool") == "get_file_summary"


@pytest.mark.asyncio
async def test_search_code_routes_to_code_index_primary(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"code_index": _SuccessCodeIndexSearchAdapter()},
        write_scope_guard=guard,
    )
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool("search_code", {"keyword": "dangerous_call"})

    assert "dangerous_call" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("mcp_adapter") == "code_index"
    assert metadata.get("mcp_tool") == "search_code_advanced"
    assert metadata.get("mcp_route_primary") == "code_index.search_code_advanced"
    assert metadata.get("mcp_route_fallback") == "filesystem.search_files"
    assert metadata.get("mcp_runtime_fallback_used") is False


@pytest.mark.asyncio
async def test_search_code_falls_back_to_filesystem_when_code_index_unavailable(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": _SuccessFilesystemSearchAdapter()},
        write_scope_guard=guard,
    )
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool("search_code", {"keyword": "dangerous_call"})

    assert "dangerous_call" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("mcp_adapter") == "filesystem"
    assert metadata.get("mcp_tool") == "search_files"
    assert metadata.get("mcp_route_primary") == "code_index.search_code_advanced"
    assert metadata.get("mcp_route_fallback") == "filesystem.search_files"
    assert metadata.get("mcp_runtime_fallback_used") is True


@pytest.mark.asyncio
async def test_list_files_routes_to_code_index_find_files(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"code_index": _SuccessCodeIndexListAdapter()},
        write_scope_guard=guard,
    )
    agent, emitter = _make_agent(tools={}, runtime=runtime)

    output = await agent.execute_tool("list_files", {"directory": "src", "pattern": "*.py"})

    assert "src/main.py" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("mcp_used") is True
    assert metadata.get("mcp_adapter") == "code_index"
    assert metadata.get("mcp_tool") == "find_files"


@pytest.mark.asyncio
async def test_runtime_anchors_filesystem_lookup_to_scan_project_root(tmp_path):
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": _CaptureFilesystemAdapter()},
        project_root=str(tmp_path),
    )

    result = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "./src/main.py"},
    )

    assert result.success is True
    adapter = runtime.adapters["filesystem"]
    assert isinstance(adapter, _CaptureFilesystemAdapter)
    assert adapter.calls
    tool_name, arguments = adapter.calls[0]
    assert tool_name == "read_file"
    assert arguments.get("path") == os.path.join(str(tmp_path), "src/main.py")


@pytest.mark.asyncio
async def test_runtime_injects_code_index_project_anchor_for_search(tmp_path):
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"code_index": _CaptureCodeIndexAdapter()},
        project_root=str(tmp_path),
    )

    result = await runtime.execute_tool(
        tool_name="list_files",
        tool_input={"directory": "src", "pattern": "*.py"},
    )

    assert result.success is True
    adapter = runtime.adapters["code_index"]
    assert isinstance(adapter, _CaptureCodeIndexAdapter)
    assert adapter.calls
    tool_name, arguments = adapter.calls[0]
    assert tool_name == "find_files"
    assert arguments.get("project_root") == str(tmp_path)
    assert arguments.get("project_path") == str(tmp_path)
    assert arguments.get("path") == "src"


@pytest.mark.asyncio
async def test_tool_failure_triggers_superpowers_retry_and_recovery(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=False,
        prefer_mcp=False,
        adapters={},
        write_scope_guard=guard,
    )
    flaky_tool = _FlakyReadTool()
    agent, emitter = _make_agent(tools={"read_file": flaky_tool}, runtime=runtime)

    output = await agent.execute_tool("read_file", {"file_path": "src/a.py"})

    assert "recovered-content" in output
    assert flaky_tool.execute_calls >= 2
    info_events = _events_by_type(emitter, "info")
    assert any("superpowers skill" in str(item.message) for item in info_events)


def test_build_task_mcp_runtime_enables_sequential_and_qmd_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", True)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    assert "filesystem" in runtime.domain_adapters
    assert "sequentialthinking" in runtime.domain_adapters
    assert "qmd" in runtime.domain_adapters
    assert runtime.required_mcps == ["filesystem"]
    assert runtime.project_root == str(tmp_path)


def test_build_task_mcp_runtime_prefers_qmd_http_even_when_stdio_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_BACKEND_URL", "http://localhost:8181/mcp")
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_URL", "http://localhost:8181/mcp")
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.FastMCPHttpAdapter.is_available",
        lambda self: True,
    )

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
        prefer_stdio_when_http_unavailable=True,
    )

    backend_qmd = runtime.domain_adapters["qmd"]["backend"]
    sandbox_qmd = runtime.domain_adapters["qmd"]["sandbox"]
    assert isinstance(backend_qmd, QmdLazyIndexAdapter)
    assert isinstance(sandbox_qmd, QmdLazyIndexAdapter)
    assert isinstance(getattr(backend_qmd, "_adapter", None), FastMCPHttpAdapter)
    assert isinstance(getattr(sandbox_qmd, "_adapter", None), FastMCPHttpAdapter)


def test_build_task_mcp_runtime_active_mcp_ids_limits_registered_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_BACKEND_URL", "http://localhost:8181/mcp")
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_URL", "http://localhost:8181/mcp")

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
        active_mcp_ids=["qmd"],
    )

    assert set(runtime.domain_adapters.keys()) == {"qmd"}


def test_build_task_mcp_runtime_supports_backend_and_sandbox_http_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_FORCE_STDIO", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_BACKEND_URL", "http://127.0.0.1:9901/mcp")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "http://127.0.0.1:9902/mcp")
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_FORCE_STDIO", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_BACKEND_URL", "http://127.0.0.1:9911/mcp")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "http://127.0.0.1:9912/mcp")
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    filesystem_backend = runtime.domain_adapters["filesystem"]["backend"]
    filesystem_sandbox = runtime.domain_adapters["filesystem"]["sandbox"]
    seq_backend = runtime.domain_adapters["sequentialthinking"]["backend"]
    seq_sandbox = runtime.domain_adapters["sequentialthinking"]["sandbox"]

    assert isinstance(filesystem_backend, FastMCPHttpAdapter)
    assert isinstance(filesystem_sandbox, FastMCPHttpAdapter)
    assert isinstance(seq_backend, FastMCPHttpAdapter)
    assert isinstance(seq_sandbox, FastMCPHttpAdapter)
    assert filesystem_backend.url == "http://127.0.0.1:9901/mcp"
    assert filesystem_sandbox.url == "http://127.0.0.1:9902/mcp"
    assert seq_backend.url == "http://127.0.0.1:9911/mcp"
    assert seq_sandbox.url == "http://127.0.0.1:9912/mcp"


def test_build_task_mcp_runtime_filesystem_force_stdio_ignores_http_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_FORCE_STDIO", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_BACKEND_URL", "http://127.0.0.1:9550/mcp")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "http://127.0.0.1:9551/mcp")
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    backend_adapter = runtime.domain_adapters["filesystem"]["backend"]
    sandbox_adapter = runtime.domain_adapters["filesystem"]["sandbox"]
    assert isinstance(backend_adapter, FastMCPStdioAdapter)
    assert isinstance(sandbox_adapter, FastMCPStdioAdapter)
    assert backend_adapter.args[-1] == str(tmp_path)
    assert sandbox_adapter.args[-1] == str(tmp_path)


def test_build_task_mcp_runtime_supports_sandbox_only_for_all_mcp_domains(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "http://127.0.0.1:9001/mcp")
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_URL", "http://127.0.0.1:9002/mcp")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "http://127.0.0.1:9003/mcp")
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_URL", "http://localhost:9004/mcp")

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    assert "sandbox" in runtime.domain_adapters["filesystem"]
    assert "sandbox" in runtime.domain_adapters["code_index"]
    assert "sandbox" in runtime.domain_adapters["sequentialthinking"]
    assert "sandbox" in runtime.domain_adapters["qmd"]


def test_build_task_mcp_runtime_filesystem_uses_daemon_default_url(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_FORCE_STDIO", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_DAEMON_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_DAEMON_PORT", 9770)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    filesystem_backend = runtime.domain_adapters["filesystem"]["backend"]
    filesystem_sandbox = runtime.domain_adapters["filesystem"]["sandbox"]
    assert isinstance(filesystem_backend, FastMCPHttpAdapter)
    assert isinstance(filesystem_sandbox, FastMCPHttpAdapter)
    assert filesystem_backend.url == "http://127.0.0.1:9770/mcp"
    assert filesystem_sandbox.url == "http://127.0.0.1:9770/mcp"


def test_build_task_mcp_runtime_sequential_uses_daemon_default_url(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_FORCE_STDIO", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_BACKEND_URL", "")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_PORT", 9771)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    seq_backend = runtime.domain_adapters["sequentialthinking"]["backend"]
    seq_sandbox = runtime.domain_adapters["sequentialthinking"]["sandbox"]
    assert isinstance(seq_backend, FastMCPHttpAdapter)
    assert isinstance(seq_sandbox, FastMCPHttpAdapter)
    assert seq_backend.url == "http://127.0.0.1:9771/mcp"
    assert seq_sandbox.url == "http://127.0.0.1:9771/mcp"
