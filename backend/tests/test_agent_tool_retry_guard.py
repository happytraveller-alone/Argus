from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.services.agent.agents.base import (
    RETRY_GUARD_TOOLS,
    AgentConfig,
    AgentResult,
    AgentType,
    BaseAgent,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _ReadSchema(BaseModel):
    file_path: str


class _DeterministicFailReadTool:
    args_schema = _ReadSchema

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=False, data="", error=f"文件不存在: {kwargs.get('file_path')}", metadata={})


class _SearchSchema(BaseModel):
    keyword: str


class _SuccessSearchTool:
    args_schema = _SearchSchema

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=True, data=f"ok: {kwargs.get('keyword')}", error=None, metadata={})


class _StrictDeterministicRuntime:
    strict_mode = True

    def __init__(self):
        self.calls = 0

    def can_handle(self, tool_name: str) -> bool:
        return tool_name == "get_recon_risk_queue_status"

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        self.calls += 1
        assert tool_name == "get_recon_risk_queue_status"
        return SimpleNamespace(
            handled=True,
            success=False,
            data="",
            error="'dict' object is not callable",
            metadata={
                "mcp_used": True,
                "mcp_adapter": "local_proxy",
                "mcp_runtime_mode": "strict",
            },
        )


class _StrictReadFileAutoRepairRuntime:
    strict_mode = True

    def __init__(self):
        self.calls = []

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in {"read_file", "search_code"}

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        self.calls.append((tool_name, dict(tool_input or {})))
        if tool_name == "search_code":
            return SimpleNamespace(
                handled=True,
                success=True,
                data="src/main/java/top/whgojp/modules/rce/command/CommandController.java:37",
                error=None,
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": "filesystem",
                    "mcp_runtime_mode": "strict",
                },
            )
        if tool_name == "read_file":
            file_path = str((tool_input or {}).get("file_path") or "")
            if file_path.endswith("CeshiController.java"):
                return SimpleNamespace(
                    handled=True,
                    success=False,
                    data="",
                    error=(
                        "mcp_call_failed:ENOENT: no such file or directory, open "
                        "'/tmp/deepaudit/task/JavaSecLab-1.4/src/main/java/top/whgojp/modules/rce/command/CeshiController.java'"
                    ),
                    metadata={
                        "mcp_used": True,
                        "mcp_adapter": "filesystem",
                        "mcp_runtime_mode": "strict",
                    },
                )
            if file_path.endswith("CommandController.java"):
                return SimpleNamespace(
                    handled=True,
                    success=True,
                    data="public class CommandController { ... }",
                    error=None,
                    metadata={
                        "mcp_used": True,
                        "mcp_adapter": "filesystem",
                        "mcp_runtime_mode": "strict",
                    },
                )
        return SimpleNamespace(
            handled=True,
            success=False,
            data="",
            error="mcp_unhandled_in_strict_mode",
            metadata={
                "mcp_used": True,
                "mcp_runtime_mode": "strict",
            },
        )


def _make_agent(tools):
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(name="test-agent", agent_type=AgentType.ANALYSIS)
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    return agent, emitter


def _events_by_type(emitter, event_type: str):
    events = []
    for call in emitter.emit.await_args_list:
        event_data = call.args[0]
        if event_data.event_type == event_type:
            events.append(event_data)
    return events


@pytest.mark.asyncio
async def test_execute_tool_short_circuits_after_deterministic_failures():
    read_tool = _DeterministicFailReadTool()
    agent, _emitter = _make_agent({"read_file": read_tool})

    first = await agent.execute_tool("read_file", {"file_path": "src/not_found.py"})
    second = await agent.execute_tool("read_file", {"file_path": "src/not_found.py"})
    third = await agent.execute_tool("read_file", {"file_path": "src/not_found.py"})

    assert ("工具执行失败" in first) or ("工具调用已短路" in first)
    assert ("工具执行失败" in second) or ("工具调用已短路" in second)
    assert "工具调用已短路" in third
    assert read_tool.execute_calls == 2


@pytest.mark.asyncio
async def test_execute_tool_reuses_cached_output_for_identical_success_calls():
    search_tool = _SuccessSearchTool()
    agent, emitter = _make_agent({"search_code": search_tool})

    first = await agent.execute_tool("search_code", {"keyword": "danger"})
    second = await agent.execute_tool("search_code", {"keyword": "danger"})
    third = await agent.execute_tool("search_code", {"keyword": "danger"})
    fourth = await agent.execute_tool("search_code", {"keyword": "danger"})

    assert "danger" in first
    assert "danger" in second
    assert "danger" in third
    assert "danger" in fourth
    assert search_tool.execute_calls == 1

    tool_result_events = _events_by_type(emitter, "tool_result")
    cache_hits = [event for event in tool_result_events if (event.metadata or {}).get("cache_hit") is True]
    assert len(cache_hits) >= 1
    assert all((event.metadata or {}).get("cache_policy") == "same_input_success_reuse" for event in cache_hits)


def test_retry_guard_contains_queue_status_tools():
    assert "get_recon_risk_queue_status" in RETRY_GUARD_TOOLS
    assert "get_queue_status" in RETRY_GUARD_TOOLS
    assert "dequeue_recon_risk_point" in RETRY_GUARD_TOOLS
    assert "dequeue_finding" in RETRY_GUARD_TOOLS


@pytest.mark.asyncio
async def test_strict_mcp_deterministic_failure_suppresses_retry_and_short_circuits():
    runtime = _StrictDeterministicRuntime()
    agent, emitter = _make_agent(tools={})
    agent.set_mcp_runtime(runtime)

    first = await agent.execute_tool("get_recon_risk_queue_status", {})
    second = await agent.execute_tool("get_recon_risk_queue_status", {})
    third = await agent.execute_tool("get_recon_risk_queue_status", {})

    assert "MCP 严格模式执行失败" in first
    assert "已抑制 superpowers 重试" in first
    assert "MCP 严格模式执行失败" in second
    assert "工具调用已短路" in third
    assert runtime.calls == 2

    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) >= 3

    first_metadata = tool_result_events[0].metadata or {}
    assert first_metadata.get("mcp_error") == "'dict' object is not callable"
    assert first_metadata.get("mcp_error_class") == "invalid_callable_binding"
    assert first_metadata.get("retry_suppressed") is True

    third_metadata = tool_result_events[2].metadata or {}
    assert third_metadata.get("retry_suppressed") is True


@pytest.mark.asyncio
async def test_strict_mcp_read_file_path_auto_repair_retries_once_and_succeeds():
    runtime = _StrictReadFileAutoRepairRuntime()
    agent, _emitter = _make_agent(tools={"read_file": object(), "search_code": object()})
    agent.set_mcp_runtime(runtime)

    output = await agent.execute_tool(
        "read_file",
        {"file_path": "src/main/java/top/whgojp/modules/rce/command/CeshiController.java"},
    )

    assert "CommandController" in output
    assert len(runtime.calls) >= 3
    assert runtime.calls[0][0] == "read_file"
    assert runtime.calls[1][0] == "search_code"
    assert runtime.calls[2][0] == "read_file"
    assert runtime.calls[2][1].get("file_path", "").endswith("CommandController.java")
