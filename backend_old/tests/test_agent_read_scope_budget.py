from types import SimpleNamespace

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
        self.calls = []
        self._output = output

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(success=True, data=self._output, error=None, metadata={})


@pytest.mark.asyncio
async def test_verify_reachability_read_scope_is_bounded():
    read_tool = _RecorderTool("read_file", "文件: src/time64.c\n行数: 1-160 / 500")
    locate_tool = _RecorderTool("locate_enclosing_function", "{'symbols':[]}")
    dataflow_tool = _RecorderTool("dataflow_analysis", '{"risk_level":"low"}')
    controlflow_tool = _RecorderTool("controlflow_analysis_light", '{"flow":{"path_found":true}}')
    agent = _DummyAgent(
        config=AgentConfig(name="budget-agent", agent_type=AgentType.VERIFICATION),
        llm_service=SimpleNamespace(),
        tools={
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
        },
        event_emitter=None,
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/time64.c", "line_start": 260, "line_end": 260},
    )

    assert read_tool.calls, "read_file should be called at least once"
    first_call = read_tool.calls[0]
    assert "start_line" in first_call
    assert "end_line" in first_call
    assert int(first_call["max_lines"]) <= 160
    assert int(first_call["end_line"]) >= int(first_call["start_line"])
    assert int(first_call["end_line"]) - int(first_call["start_line"]) + 1 <= 160
    assert "verify_pipeline_json:" in output
