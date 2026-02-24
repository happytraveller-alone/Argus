from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _RecorderTool:
    def __init__(self, name: str):
        self.name = name
        self.description = f"tool:{name}"
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(success=True, data={"tool": self.name, "kwargs": kwargs}, error=None, metadata={})


def _events_by_type(emitter, event_type: str):
    events = []
    for call in emitter.emit.await_args_list:
        event_data = call.args[0]
        if event_data.event_type == event_type:
            events.append(event_data)
    return events


def _make_agent(tools):
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(name="routing-agent", agent_type=AgentType.VERIFICATION)
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    return agent, emitter


@pytest.mark.asyncio
async def test_verify_reachability_routes_to_controlflow():
    read_tool = _RecorderTool("read_file")
    flow_tool = _RecorderTool("controlflow_analysis_light")
    agent, emitter = _make_agent(
        {
            "read_file": read_tool,
            "controlflow_analysis_light": flow_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/time64.c", "line_start": 168, "function_name": "asctime64_r"},
    )

    assert "controlflow_analysis_light" in output
    assert flow_tool.calls == 1
    assert read_tool.calls == 0

    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    assert metadata.get("alias_used") == "verify_reachability"


@pytest.mark.asyncio
async def test_verify_reachability_routes_to_dataflow_when_source_sink_hints_present():
    dataflow_tool = _RecorderTool("dataflow_analysis")
    controlflow_tool = _RecorderTool("controlflow_analysis_light")
    agent, _emitter = _make_agent(
        {
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {
            "source_hints": "user_input",
            "sink_hints": "sprintf",
            "variable_name": "buf",
            "file_path": "src/time64.c",
        },
    )

    assert "dataflow_analysis" in output
    assert dataflow_tool.calls == 1
    assert controlflow_tool.calls == 0


@pytest.mark.asyncio
async def test_verify_reachability_falls_back_to_read_file_when_flow_tools_absent():
    read_tool = _RecorderTool("read_file")
    agent, _emitter = _make_agent({"read_file": read_tool})

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/a.c", "line_start": 10},
    )

    assert "read_file" in output
    assert read_tool.calls == 1
