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

    assert "工具执行失败" in first
    assert "工具执行失败" in second
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
