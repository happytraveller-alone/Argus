import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _SuccessTool:
    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={"ok": True, "input": kwargs},
            error=None,
            metadata={
                "render_type": "analysis_summary",
                "display_command": "demo_tool",
                "command_chain": ["demo_tool"],
                "entries": [
                    {
                        "title": "Demo Tool Summary",
                        "summary": "ok",
                        "severity_stats": {},
                        "hit_count": 0,
                        "key_files": [],
                        "highlights": [],
                        "next_actions": [],
                    }
                ],
            },
        )


class _FailTool:
    async def execute(self, **kwargs):
        return SimpleNamespace(success=False, data="", error="failed by test", metadata={})


class _ErrorTool:
    async def execute(self, **kwargs):
        raise RuntimeError("tool exception for test")


class _SlowTool:
    async def execute(self, **kwargs):
        await asyncio.sleep(2)
        return SimpleNamespace(success=True, data="late", error=None, metadata={})


class _RequiredKeywordSchema(BaseModel):
    keyword: str


class _SearchLikeTool:
    args_schema = _RequiredKeywordSchema

    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data={"keyword": kwargs.get("keyword")}, error=None, metadata={})


class _McpSuccessRuntime:
    router = SimpleNamespace(can_route=lambda *_: True)

    def can_handle(self, tool_name):
        return tool_name == "demo_tool"

    def should_prefer_mcp(self):
        return True

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        return SimpleNamespace(
            handled=True,
            success=True,
            data="mcp ok",
            error=None,
            metadata={
                "render_type": "analysis_summary",
                "display_command": tool_name,
                "command_chain": [tool_name],
                "entries": [
                    {
                        "title": "MCP Summary",
                        "summary": "ok",
                        "severity_stats": {},
                        "hit_count": 0,
                        "key_files": [],
                        "highlights": [],
                        "next_actions": [],
                    }
                ],
            },
            should_fallback=False,
        )


class _McpFallbackRuntime:
    router = SimpleNamespace(can_route=lambda *_: True)

    def can_handle(self, tool_name):
        return tool_name == "demo_tool"

    def should_prefer_mcp(self):
        return True

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        return SimpleNamespace(
            handled=True,
            success=False,
            data="mcp failed",
            error="adapter down",
            metadata={"mcp_runtime_domain": "stdio"},
            should_fallback=True,
        )


def _make_agent(tool_name: str, tool_impl):
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(name="test-agent", agent_type=AgentType.ANALYSIS)
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools={tool_name: tool_impl},
        event_emitter=emitter,
    )
    return agent, emitter


def _get_events_by_type(emitter, event_type: str):
    events = []
    for call in emitter.emit.await_args_list:
        event_data = call.args[0]
        if event_data.event_type == event_type:
            events.append(event_data)
    return events


@pytest.mark.asyncio
async def test_tool_call_and_result_share_same_tool_call_id():
    agent, emitter = _make_agent("demo_tool", _SuccessTool())

    output = await agent.execute_tool("demo_tool", {"path": "a.py"})
    assert output

    tool_call_events = _get_events_by_type(emitter, "tool_call")
    tool_result_events = _get_events_by_type(emitter, "tool_result")

    assert len(tool_call_events) == 1
    assert len(tool_result_events) == 1

    call_event = tool_call_events[0]
    result_event = tool_result_events[0]

    assert call_event.metadata is not None
    assert result_event.metadata is not None
    assert call_event.metadata.get("tool_call_id")
    assert result_event.metadata.get("tool_call_id")
    assert call_event.metadata["tool_call_id"] == result_event.metadata["tool_call_id"]
    assert result_event.metadata.get("tool_status") == "completed"
    assert result_event.tool_output["metadata"]["render_type"] == "analysis_summary"
    assert "render_type" not in (result_event.metadata or {})


@pytest.mark.asyncio
async def test_tool_status_terminal_failed_for_error_result():
    agent, emitter = _make_agent("fail_tool", _FailTool())

    output = await agent.execute_tool("fail_tool", {"arg": 1})
    assert "工具执行失败" in output

    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    assert tool_result_events[0].metadata.get("tool_status") == "failed"
    assert tool_result_events[0].tool_output.get("error") == "failed by test"


@pytest.mark.asyncio
async def test_tool_status_terminal_failed_for_exception():
    agent, emitter = _make_agent("error_tool", _ErrorTool())

    output = await agent.execute_tool("error_tool", {"arg": 2})
    assert "工具执行异常" in output

    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    assert tool_result_events[0].metadata.get("tool_status") == "failed"


@pytest.mark.asyncio
async def test_tool_status_terminal_cancelled():
    agent, emitter = _make_agent("slow_tool", _SlowTool())

    execution_task = asyncio.create_task(agent.execute_tool("slow_tool", {"arg": 3}))
    await asyncio.sleep(0.1)
    agent.cancel()
    output = await execution_task

    assert "任务已取消" in output
    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    assert tool_result_events[0].metadata.get("tool_status") == "cancelled"


@pytest.mark.asyncio
async def test_tool_validation_missing_required_field_returns_recoverable_error():
    agent, emitter = _make_agent("search_code", _SearchLikeTool())

    output = await agent.execute_tool("search_code", {})

    assert "工具参数校验失败" in output
    assert "keyword" in output
    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    assert tool_result_events[0].metadata.get("tool_status") == "failed"
    assert tool_result_events[0].metadata.get("validation_error")


@pytest.mark.asyncio
async def test_tool_result_keeps_native_metadata_for_mcp_success():
    agent, emitter = _make_agent("demo_tool", _SuccessTool())
    agent.set_mcp_runtime(_McpSuccessRuntime())

    output = await agent.execute_tool("demo_tool", {"path": "a.py"})

    assert output == "mcp ok"
    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    result_event = tool_result_events[0]
    assert result_event.metadata.get("tool_status") == "completed"
    assert result_event.tool_output["metadata"]["display_command"] == "demo_tool"
    assert result_event.metadata.get("mcp_used") is True


@pytest.mark.asyncio
async def test_tool_result_keeps_native_metadata_for_mcp_fallback_success():
    agent, emitter = _make_agent("demo_tool", _SuccessTool())
    agent.set_mcp_runtime(_McpFallbackRuntime())

    output = await agent.execute_tool("demo_tool", {"path": "a.py"})

    assert output
    tool_result_events = _get_events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    result_event = tool_result_events[0]
    assert result_event.metadata.get("tool_status") == "completed"
    assert result_event.metadata.get("mcp_fallback_used") is True
    assert result_event.tool_output["metadata"]["render_type"] == "analysis_summary"
