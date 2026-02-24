import pytest

from app.services.agent.mcp.runtime import MCPRuntime


class _DomainAdapter:
    def __init__(self, *, runtime_domain: str, marker: str, available: bool = True):
        self.runtime_domain = runtime_domain
        self.marker = marker
        self._available = available

    def is_available(self) -> bool:
        return self._available

    async def call_tool(self, tool_name, arguments):
        return {
            "success": True,
            "data": f"{self.marker}:{tool_name}",
            "metadata": {"marker": self.marker},
        }


@pytest.mark.asyncio
async def test_dual_runtime_prefers_backend_when_both_available():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "filesystem": {
                "backend": _DomainAdapter(runtime_domain="backend", marker="backend"),
                "sandbox": _DomainAdapter(runtime_domain="sandbox", marker="sandbox"),
            }
        },
        runtime_modes={"filesystem": "backend_then_sandbox"},
        required_mcps=["filesystem"],
    )

    result = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "src/main.c"},
    )

    assert result.success is True
    assert "backend:read_file" in result.data
    assert result.metadata.get("mcp_runtime_domain") == "backend"


@pytest.mark.asyncio
async def test_dual_runtime_falls_back_to_sandbox_when_backend_unavailable():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "filesystem": {
                "backend": _DomainAdapter(
                    runtime_domain="backend",
                    marker="backend",
                    available=False,
                ),
                "sandbox": _DomainAdapter(runtime_domain="sandbox", marker="sandbox"),
            }
        },
        runtime_modes={"filesystem": "backend_then_sandbox"},
        required_mcps=["filesystem"],
    )

    result = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "src/main.c"},
    )

    assert result.success is True
    assert "sandbox:read_file" in result.data
    assert result.metadata.get("mcp_runtime_domain") == "sandbox"
