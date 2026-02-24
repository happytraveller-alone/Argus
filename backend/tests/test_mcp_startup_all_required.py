import pytest

from app.services.agent.mcp.runtime import MCPRuntime


class _DummyAdapter:
    def __init__(self, *, runtime_domain: str, available: bool = True):
        self.runtime_domain = runtime_domain
        self._available = available

    def is_available(self) -> bool:
        return self._available

    async def call_tool(self, tool_name, arguments):
        return {"success": True, "data": f"{tool_name}:{arguments}"}


def test_ensure_all_mcp_ready_requires_all_domains_when_domain_is_all():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "filesystem": {
                "backend": _DummyAdapter(runtime_domain="backend"),
                "sandbox": _DummyAdapter(runtime_domain="sandbox"),
            },
            "qmd": {
                "backend": _DummyAdapter(runtime_domain="backend"),
            },
        },
        runtime_modes={
            "filesystem": "backend_then_sandbox",
            "qmd": "backend_then_sandbox",
        },
        required_mcps=["filesystem", "qmd"],
    )

    readiness = runtime.ensure_all_mcp_ready("all")
    assert readiness["ready"] is False
    not_ready = readiness.get("not_ready") or []
    assert any(
        item.get("mcp") == "qmd"
        and item.get("runtime_domain") == "sandbox"
        and item.get("reason") == "domain_adapter_missing"
        for item in not_ready
    )


def test_ensure_all_mcp_ready_backend_only_passes_when_backend_ready():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "filesystem": {
                "backend": _DummyAdapter(runtime_domain="backend"),
                "sandbox": _DummyAdapter(runtime_domain="sandbox", available=False),
            },
            "qmd": {
                "backend": _DummyAdapter(runtime_domain="backend"),
            },
        },
        runtime_modes={
            "filesystem": "backend_then_sandbox",
            "qmd": "backend_then_sandbox",
        },
        required_mcps=["filesystem", "qmd"],
    )

    readiness = runtime.ensure_all_mcp_ready("backend")
    assert readiness["ready"] is True
    assert readiness.get("not_ready") == []


@pytest.mark.asyncio
async def test_execute_tool_returns_skip_reason_when_runtime_domain_has_no_adapter():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "filesystem": {
                "backend": _DummyAdapter(runtime_domain="backend"),
            }
        },
        runtime_modes={"filesystem": "sandbox_only"},
        required_mcps=["filesystem"],
    )

    result = await runtime.execute_tool(
        tool_name="read_file",
        tool_input={"file_path": "src/main.c"},
    )

    assert result.handled is True
    assert result.success is False
    assert result.should_fallback is True
    assert (result.metadata or {}).get("mcp_skipped") is True
    assert (result.metadata or {}).get("mcp_skip_reason") == "adapter_unavailable"
