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
    def __init__(self, name: str, output: str):
        self.name = name
        self.description = f"tool:{name}"
        self.calls = 0
        self.call_inputs = []
        self._output = output

    async def execute(self, **kwargs):
        self.calls += 1
        self.call_inputs.append(kwargs)
        return SimpleNamespace(success=True, data=self._output, error=None, metadata={})


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
async def test_verify_reachability_runs_pipeline_sequence():
    read_tool = _RecorderTool("read_file", "文件: src/time64.c\n行数: 128-180 / 360")
    locate_tool = _RecorderTool(
        "locate_enclosing_function",
        "{'symbols':[{'name':'asctime64_r','kind':'function','start_line':120,'end_line':240}]}",
    )
    extract_tool = _RecorderTool("extract_function", "function body")
    dataflow_tool = _RecorderTool(
        "dataflow_analysis",
        '{"risk_level":"medium","taint_steps":["source->asctime64_r","asctime64_r->stack_overflow_risk"]}',
    )
    controlflow_tool = _RecorderTool(
        "controlflow_analysis_light",
        '{"flow":{"path_found":true,"path_score":0.72}}',
    )
    agent, emitter = _make_agent(
        {
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "extract_function": extract_tool,
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/time64.c", "line_start": 168, "line_end": 168},
    )

    assert "verify_reachability pipeline completed" in output
    assert "reachability: reachable" in output
    assert read_tool.calls == 1
    assert locate_tool.calls == 1
    assert extract_tool.calls == 1
    assert dataflow_tool.calls == 1
    assert controlflow_tool.calls == 1

    tool_call_events = _events_by_type(emitter, "tool_call")
    ordered_names = [event.tool_name for event in tool_call_events]
    assert ordered_names == [
        "verify_reachability",
        "read_file",
        "locate_enclosing_function",
        "extract_function",
        "dataflow_analysis",
        "controlflow_analysis_light",
    ]


@pytest.mark.asyncio
async def test_verify_reachability_uses_search_when_location_missing():
    search_tool = _RecorderTool("search_code", "src/authz.c:88\n`if (!is_admin(user)) return`")
    read_tool = _RecorderTool("read_file", "文件: src/authz.c\n行数: 48-120 / 320")
    locate_tool = _RecorderTool("locate_enclosing_function", "{'symbols':[]}")
    dataflow_tool = _RecorderTool("dataflow_analysis", '{"risk_level":"low"}')
    controlflow_tool = _RecorderTool("controlflow_analysis_light", '{"flow":{"path_found":true}}')
    agent, _emitter = _make_agent(
        {
            "search_code": search_tool,
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"vulnerability_type": "authz_bypass", "sink_hints": ["is_admin"]},
    )

    assert search_tool.calls == 1
    assert "location: src/authz.c:88" in output
    assert "verify_reachability pipeline completed" in output
    assert "reachability: reachable" in output


@pytest.mark.asyncio
async def test_verify_reachability_marks_unreachable_from_lightweight_negative_signal():
    read_tool = _RecorderTool("read_file", "文件: src/demo.c\n行数: 1-80 / 200")
    locate_tool = _RecorderTool("locate_enclosing_function", "{'symbols':[]}")
    dataflow_tool = _RecorderTool("dataflow_analysis", '{"risk_level":"low"}')
    controlflow_tool = _RecorderTool("controlflow_analysis_light", '{"flow":{"path_found":false}}')
    agent, _ = _make_agent(
        {
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/demo.c", "line_start": 12, "line_end": 12},
    )

    assert "reachability: unreachable" in output
