from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import MCPRuntime, TaskWriteScopeGuard


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _SuccessfulFilesystemAdapter:
    async def call_tool(self, tool_name, arguments):
        return {
            "success": True,
            "data": f"ok:{tool_name}:{arguments.get('path')}",
            "metadata": {"adapter": "filesystem"},
        }


def _make_agent(agent_type: AgentType, runtime: MCPRuntime) -> _DummyAgent:
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(name=f"dummy-{agent_type.value}", agent_type=agent_type),
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=emitter,
    )
    agent.set_mcp_runtime(runtime)
    return agent


@pytest.mark.asyncio
async def test_all_agent_types_have_write_entrypoint_with_same_guard(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": _SuccessfulFilesystemAdapter()},
        write_scope_guard=guard,
    )

    agents = [
        _make_agent(AgentType.RECON, runtime),
        _make_agent(AgentType.ANALYSIS, runtime),
        _make_agent(AgentType.VERIFICATION, runtime),
        _make_agent(AgentType.ORCHESTRATOR, runtime),
    ]

    for idx, agent in enumerate(agents):
        output = await agent.execute_tool(
            "edit_file",
            {
                "file_path": f"src/verified_{idx}.py",
                "old_text": "a",
                "new_text": "b",
                "reason": "verified remediation",
                "finding_id": f"finding-{idx}",
            },
        )
        assert "ok:edit_file" in output

    assert len(guard.writable_files) == 4


@pytest.mark.asyncio
async def test_all_agent_types_are_constrained_by_same_write_guard(tmp_path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path), max_writable_files_per_task=50)
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": _SuccessfulFilesystemAdapter()},
        write_scope_guard=guard,
    )

    agents = [
        _make_agent(AgentType.RECON, runtime),
        _make_agent(AgentType.ANALYSIS, runtime),
        _make_agent(AgentType.VERIFICATION, runtime),
        _make_agent(AgentType.ORCHESTRATOR, runtime),
    ]

    for agent in agents:
        output = await agent.execute_tool(
            "write_file",
            {
                "file_path": "src/not_allowlisted.py",
                "content": "print('test')",
            },
        )
        assert "写入策略校验失败" in output
        assert "目标文件不在证据绑定白名单" in output

    assert len(guard.writable_files) == 0
