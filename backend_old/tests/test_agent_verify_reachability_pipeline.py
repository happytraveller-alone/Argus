from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
import app.models.opengrep  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _LocalTool:
    def __init__(self, name: str, output: str):
        self.name = name
        self.description = f"tool:{name}"
        self.execute_calls = 0
        self._output = output
        self.execute_kwargs = []

    async def execute(self, **kwargs):
        self.execute_calls += 1
        self.execute_kwargs.append(dict(kwargs))
        return SimpleNamespace(success=True, data=self._output, error=None, metadata={})


def _make_agent(tools):
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(name="verify-pipeline", agent_type=AgentType.VERIFICATION),
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    return agent


@pytest.mark.asyncio
async def test_verify_reachability_pipeline_reports_insufficient_flow_without_flow_tools():
    read_tool = _LocalTool("read_file", "local read")
    locate_tool = _LocalTool("locate_enclosing_function", "{'symbols':[]}")
    agent = _make_agent(
        {
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/demo.c", "line_start": 12},
    )

    assert "verify_reachability 执行错误" in output
    assert "blocked_reason: insufficient_flow_evidence" in output
    assert read_tool.execute_calls == 0
    assert locate_tool.execute_calls == 1


@pytest.mark.asyncio
async def test_verify_reachability_pipeline_completes_without_deep_verifier():
    read_tool = _LocalTool("read_file", "文件: src/demo.c\n行数: 1-80 / 200")
    locate_tool = _LocalTool(
        "locate_enclosing_function",
        "{'symbols':[{'name':'target','kind':'function','start_line':10,'end_line':90}]}",
    )
    extract_tool = _LocalTool("extract_function", "function body")
    dataflow_tool = _LocalTool("dataflow_analysis", '{"risk_level":"medium"}')
    controlflow_tool = _LocalTool("controlflow_analysis_light", '{"flow":{"path_found":true}}')

    agent = _make_agent(
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
        {"file_path": "src/demo.c", "line_start": 20},
    )

    assert "verify_reachability pipeline completed" in output
    assert "reachability: reachable" in output
    assert extract_tool.execute_kwargs == [{"path": "src/demo.c", "symbol_name": "target"}]


@pytest.mark.asyncio
async def test_verify_reachability_pipeline_prefers_covering_symbol_from_locator_payload():
    read_tool = _LocalTool("read_file", "文件: src/demo.py\n行数: 1-40 / 40")
    locate_tool = _LocalTool(
        "locate_enclosing_function",
        str(
            {
                "file_path": "src/demo.py",
                "line_start": 3,
                "enclosing_function": {
                    "name": "wrapper",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                },
                "symbols": [
                    {
                        "name": "wrapper",
                        "kind": "function",
                        "start_line": 1,
                        "end_line": 10,
                        "language": "python",
                    },
                    {
                        "name": "target",
                        "kind": "function",
                        "start_line": 2,
                        "end_line": 4,
                        "language": "python",
                    },
                ],
                "diagnostics": ["python_tree_sitter"],
            }
        ),
    )
    extract_tool = _LocalTool("extract_function", "function body")
    dataflow_tool = _LocalTool("dataflow_analysis", '{"risk_level":"medium"}')
    controlflow_tool = _LocalTool("controlflow_analysis_light", '{"flow":{"path_found":true}}')

    agent = _make_agent(
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
        {"file_path": "src/demo.py", "line_start": 3},
    )

    assert "verify_reachability pipeline completed" in output
    assert extract_tool.execute_calls == 1
    assert extract_tool.execute_kwargs[0]["symbol_name"] == "target"
