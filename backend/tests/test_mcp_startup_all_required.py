import pytest

from app.api.v1.endpoints.agent_tasks import _probe_required_mcp_runtime
from app.services.agent.mcp.runtime import MCPRuntime


class _DummyAdapter:
    def __init__(self, *, runtime_domain: str, available: bool = True, tools=None):
        self.runtime_domain = runtime_domain
        self._available = available
        self._tools = list(tools or [{"name": "status", "description": "", "inputSchema": {}}])

    def is_available(self) -> bool:
        return self._available

    async def list_tools(self):
        return list(self._tools)

    async def call_tool(self, tool_name, arguments):
        return {"success": True, "data": f"{tool_name}:{arguments}"}


class _ProbeInfraFailAdapter(_DummyAdapter):
    async def list_tools(self):
        return [{"name": "read_file", "description": "", "inputSchema": {"type": "object"}}]

    async def call_tool(self, tool_name, arguments):
        raise RuntimeError("Server disconnected without sending a response.")


class _RecorderAdapter(_DummyAdapter):
    def __init__(self, *, runtime_domain: str, available: bool = True, tools=None):
        super().__init__(runtime_domain=runtime_domain, available=available, tools=tools)
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        return {"success": True, "data": "ok"}


def test_ensure_all_mcp_ready_all_passes_when_any_domain_ready():
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
    assert readiness["ready"] is True
    assert readiness.get("not_ready") == []


def test_ensure_all_mcp_ready_all_respects_backend_only_runtime_mode():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "qmd": {
                "backend": _DummyAdapter(runtime_domain="backend"),
            },
        },
        runtime_modes={"qmd": "backend_only"},
        required_mcps=["qmd"],
    )

    readiness = runtime.ensure_all_mcp_ready("all")
    assert readiness["ready"] is True
    assert readiness.get("not_ready") == []


def test_ensure_all_mcp_ready_all_passes_when_dual_domains_ready():
    runtime = MCPRuntime(
        enabled=True,
        domain_adapters={
            "code_index": {
                "backend": _DummyAdapter(runtime_domain="backend"),
                "sandbox": _DummyAdapter(runtime_domain="sandbox"),
            },
            "qmd": {
                "backend": _DummyAdapter(runtime_domain="backend"),
                "sandbox": _DummyAdapter(runtime_domain="sandbox"),
            },
        },
        runtime_modes={
            "code_index": "backend_then_sandbox",
            "qmd": "backend_then_sandbox",
        },
        required_mcps=["code_index", "qmd"],
    )

    readiness = runtime.ensure_all_mcp_ready("all")
    assert readiness["ready"] is True
    assert readiness.get("not_ready") == []


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


@pytest.mark.asyncio
async def test_probe_required_mcp_runtime_reports_infra_failure():
    runtime = MCPRuntime(
        enabled=True,
        adapters={"filesystem": _ProbeInfraFailAdapter(runtime_domain="backend")},
        required_mcps=["filesystem"],
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="backend")

    assert probe["ready"] is False
    not_ready = probe.get("not_ready") or []
    assert any(item.get("mcp") == "filesystem" for item in not_ready)


@pytest.mark.asyncio
async def test_probe_required_mcp_runtime_uses_filesystem_read_file_tool(tmp_path):
    filesystem = _RecorderAdapter(
        runtime_domain="backend",
        tools=[
            {
                "name": "read_file",
                "description": "",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
    )
    runtime = MCPRuntime(
        enabled=True,
        adapters={"filesystem": filesystem},
        required_mcps=["filesystem"],
        project_root=str(tmp_path),
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="backend")

    assert probe["ready"] is True
    assert filesystem.calls and filesystem.calls[0][0] == "read_file"
    assert ".mcp_required_filesystem_probe.txt" in str(filesystem.calls[0][1]["path"])


@pytest.mark.asyncio
async def test_probe_required_mcp_runtime_uses_qmd_and_sequential_tools():
    qmd = _RecorderAdapter(
        runtime_domain="backend",
        tools=[{"name": "status", "description": "", "inputSchema": {}}],
    )
    sequential = _RecorderAdapter(
        runtime_domain="backend",
        tools=[
            {
                "name": "sequentialthinking",
                "description": "",
                "inputSchema": {
                    "type": "object",
                    "properties": {"thought": {"type": "string"}},
                    "required": ["thought"],
                },
            }
        ],
    )
    runtime = MCPRuntime(
        enabled=True,
        adapters={
            "qmd": qmd,
            "sequentialthinking": sequential,
        },
        required_mcps=["qmd", "sequentialthinking"],
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="backend")

    assert probe["ready"] is True
    assert qmd.calls and qmd.calls[0][0] == "status"
    assert sequential.calls and sequential.calls[0][0] == "sequentialthinking"
