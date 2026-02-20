from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel
import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _SearchSchema(BaseModel):
    keyword: str


class _SearchTool:
    args_schema = _SearchSchema

    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data={"keyword": kwargs.get("keyword")}, error=None, metadata={})


def _make_agent():
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(name="test-agent", agent_type=AgentType.ANALYSIS)
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools={"search_code": _SearchTool()},
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
async def test_execute_tool_repairs_query_to_keyword():
    agent, emitter = _make_agent()

    output = await agent.execute_tool("search_code", {"query": "danger"})

    assert "danger" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    assert metadata.get("input_repaired") == {"query": "keyword"}


@pytest.mark.asyncio
async def test_execute_tool_resolves_alias_to_available_tool():
    agent, emitter = _make_agent()

    output = await agent.execute_tool("rag_query", {"query": "auth"})

    assert "auth" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    call_event = tool_call_events[0]
    assert call_event.tool_name == "search_code"
    metadata = call_event.metadata or {}
    assert metadata.get("alias_used") == "rag_query"
