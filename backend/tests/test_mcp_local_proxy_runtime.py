from types import SimpleNamespace

import pytest

from app.services.agent.mcp.runtime import MCPRuntime


class _LocalEchoTool:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            success=True,
            data=f"echo:{kwargs.get('value')}",
            error=None,
            metadata={"local_tool": True},
            duration_ms=1,
        )


class _ReadAdapter:
    runtime_domain = "backend"

    def __init__(self) -> None:
        self.calls = 0

    def is_available(self) -> bool:
        return True

    async def call_tool(self, tool_name, arguments):
        self.calls += 1
        assert tool_name == "read_file"
        return {
            "success": True,
            "data": f"read:{arguments.get('path')}",
            "metadata": {"adapter": "filesystem"},
        }


@pytest.mark.asyncio
async def test_runtime_registers_local_proxy_tools_and_executes_via_mcp():
    runtime = MCPRuntime(enabled=True, prefer_mcp=True, adapters={})
    tool = _LocalEchoTool()

    registered = runtime.register_local_tool("echo_tool", tool)
    assert registered is True
    assert runtime.can_handle("echo_tool") is True

    result = await runtime.execute_tool(
        tool_name="echo_tool",
        tool_input={"value": "ok"},
        agent_name="analysis",
    )

    assert result.handled is True
    assert result.success is True
    assert result.data == "echo:ok"
    assert result.metadata.get("local_proxy") is True
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_runtime_retrieval_cache_dedupes_same_read_file_request():
    adapter = _ReadAdapter()
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": adapter},
    )

    first = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "src/main.py"},
    )
    second = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "src/main.py"},
    )

    assert first.success is True
    assert second.success is True
    assert second.metadata.get("cache_hit") is True
    assert second.metadata.get("mcp_runtime_cache_hit") is True
    assert adapter.calls == 1
