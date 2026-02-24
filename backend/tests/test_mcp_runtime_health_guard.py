import pytest

from app.services.agent.mcp.runtime import FastMCPStdioAdapter, MCPRuntime


class _AlwaysFailAdapter:
    runtime_domain = "backend"

    def is_available(self) -> bool:
        return True

    async def call_tool(self, tool_name, arguments):
        raise FileNotFoundError("No such file or directory")


def test_fastmcp_stdio_adapter_reports_unavailable_when_command_missing():
    adapter = FastMCPStdioAdapter(command="definitely-not-a-real-command-xyz")
    assert adapter.is_available() is False
    assert adapter.availability_reason == "command_not_found"


def test_runtime_can_handle_is_false_when_adapter_command_missing():
    adapter = FastMCPStdioAdapter(command="definitely-not-a-real-command-xyz")
    runtime = MCPRuntime(
        enabled=True,
        adapters={"filesystem": adapter},
    )

    assert runtime.can_handle("read_file") is False


@pytest.mark.asyncio
async def test_runtime_marks_adapter_disabled_after_repeated_infra_failures():
    runtime = MCPRuntime(
        enabled=True,
        adapters={"filesystem": _AlwaysFailAdapter()},
        adapter_failure_threshold=2,
    )

    # Two failures trip the circuit breaker.
    for _ in range(2):
        await runtime.execute_tool(
            tool_name="read_file",
            tool_input={"file_path": "src/a.c"},
        )

    assert runtime.can_handle("read_file") is False
