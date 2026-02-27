from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import MCPRuntime
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _LocalTool:
    def __init__(self, name: str, output: str):
        self.name = name
        self.description = f"tool:{name}"
        self.execute_calls = 0
        self._output = output

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=True, data=self._output, error=None, metadata={})


def _make_agent(tools, runtime=None):
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(name="verify-pipeline", agent_type=AgentType.VERIFICATION),
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    if runtime is not None:
        agent.set_mcp_runtime(runtime)
    return agent


@pytest.mark.asyncio
async def test_verify_reachability_pipeline_blocks_when_mcp_strict_mode_has_no_route():
    read_tool = _LocalTool("read_file", "local read")
    locate_tool = _LocalTool("locate_enclosing_function", "{'symbols':[]}")
    joern_tool = _LocalTool("joern_reachability_verify", '{"path_found": true}')
    cpg_tool = _LocalTool("cpg_query", '{"path_found": true}')
    runtime = MCPRuntime(enabled=True, prefer_mcp=True, adapters={}, strict_mode=True)
    agent = _make_agent(
        {
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "joern_reachability_verify": joern_tool,
            "cpg_query": cpg_tool,
        },
        runtime=runtime,
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/demo.c", "line_start": 12},
    )

    assert "verify_reachability 执行错误" in output
    assert "blocked_reason: mcp_unavailable" in output
    assert read_tool.execute_calls == 0
    assert locate_tool.execute_calls == 0
    assert joern_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_verify_reachability_maps_mcp_disconnect_to_mcp_unavailable():
    read_tool = _LocalTool("read_file", "文件: src/demo.c\n行数: 1-80 / 200")
    locate_tool = _LocalTool(
        "locate_enclosing_function",
        "{'symbols':[{'name':'target','kind':'function','start_line':10,'end_line':90}]}",
    )
    extract_tool = _LocalTool("extract_function", "function body")
    dataflow_tool = _LocalTool("dataflow_analysis", '{"risk_level":"medium"}')
    controlflow_tool = _LocalTool("controlflow_analysis_light", '{"flow":{"path_found":true}}')
    joern_tool = _LocalTool(
        "joern_reachability_verify",
        "⚠️ MCP 工具执行失败\n\n错误: mcp_call_failed: Server disconnected without sending a response.",
    )
    cpg_tool = _LocalTool("cpg_query", '{"path_found": true}')

    agent = _make_agent(
        {
            "read_file": read_tool,
            "locate_enclosing_function": locate_tool,
            "extract_function": extract_tool,
            "dataflow_analysis": dataflow_tool,
            "controlflow_analysis_light": controlflow_tool,
            "joern_reachability_verify": joern_tool,
            "cpg_query": cpg_tool,
        }
    )

    output = await agent.execute_tool(
        "verify_reachability",
        {"file_path": "src/demo.c", "line_start": 20},
    )

    assert "verify_reachability 执行错误" in output
    assert "blocked_reason: mcp_unavailable" in output
