from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime
from app.core.config import settings
from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import MCPRuntime, TaskWriteScopeGuard


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


def _make_agent(*, tools, runtime):
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(name="test-agent", agent_type=AgentType.ANALYSIS),
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
async def test_mcp_failure_for_read_file_can_fallback_to_local_tool(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        write_scope_guard=guard,
    )
    local_read_tool = _LocalReadTool()
    agent, _ = _make_agent(tools={"read_file": local_read_tool}, runtime=runtime)

    output = await agent.execute_tool("read_file", {"file_path": "src/sql_vuln.py"})

    assert "local-read:src/sql_vuln.py" in output
    assert local_read_tool.execute_calls == 1


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


def test_build_task_mcp_runtime_enables_memory_and_sequential_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_MEMORY_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", True)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    assert "filesystem" in runtime.adapters
    assert "memory" in runtime.adapters
    assert "sequentialthinking" in runtime.adapters
