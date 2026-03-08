from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime, _probe_required_mcp_runtime
from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import FastMCPStdioAdapter, MCPRuntime, MCPToolRouter


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _ReadSchema(BaseModel):
    file_path: str


class _LocalReadTool:
    args_schema = _ReadSchema
    name = "read_file"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(
            success=True,
            data=f"local-read:{kwargs.get('file_path')}",
            error=None,
            metadata={"file_path": kwargs.get("file_path")},
        )


class _ProbeAdapter:
    runtime_domain = "stdio"

    def __init__(self, *, tools, call_result=None):
        self._tools = tools
        self._call_result = call_result or {"success": True, "data": "ok", "metadata": {}}
        self.calls = []

    def is_available(self) -> bool:
        return True

    async def list_tools(self):
        return list(self._tools)

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        if callable(self._call_result):
            return self._call_result(tool_name, arguments)
        return dict(self._call_result)


def _make_agent(*, tools, runtime, metadata=None):
    emitter = SimpleNamespace(emit=AsyncMock())
    agent = _DummyAgent(
        config=AgentConfig(
            name="test-agent",
            agent_type=AgentType.ANALYSIS,
            metadata=metadata or {},
        ),
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    agent.set_mcp_runtime(runtime)
    return agent


@pytest.mark.asyncio
async def test_task_mcp_runtime_uses_only_stdio_adapters(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr(
        "app.core.config.settings.MCP_FILESYSTEM_ARGS",
        "-c 'print(\"filesystem\")'",
    )
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_COMMAND", "python3")
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODE_INDEX_ARGS",
        "-c 'print(\"code-index\")'",
    )

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=[],
    )

    assert isinstance(runtime, MCPRuntime)
    assert set(runtime.adapters.keys()) == {"filesystem", "code_index"}
    assert "local_proxy" not in runtime.adapters
    assert runtime.domain_adapters == {}
    assert isinstance(runtime.adapters["filesystem"], FastMCPStdioAdapter)
    assert isinstance(runtime.adapters["code_index"], FastMCPStdioAdapter)
    assert runtime.default_runtime_mode == "stdio_only"
    assert runtime.runtime_modes == {
        "filesystem": "stdio_only",
        "code_index": "stdio_only",
    }


@pytest.mark.asyncio
async def test_task_mcp_runtime_injects_project_root_into_filesystem_stdio_args(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "pnpm")
    monkeypatch.setattr(
        "app.core.config.settings.MCP_FILESYSTEM_ARGS",
        "dlx @modelcontextprotocol/server-filesystem",
    )
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=[],
    )

    filesystem_adapter = runtime.adapters["filesystem"]
    assert str(tmp_path) in filesystem_adapter.args


def test_mcp_router_exposes_only_core_stdio_routes():
    router = MCPToolRouter()

    read_route = router.route("read_file", {"file_path": "src/main.py"})
    assert read_route is not None
    assert read_route.adapter_name == "filesystem"
    assert read_route.mcp_tool_name == "read_file"
    assert read_route.arguments["path"] == "src/main.py"

    search_route = router.route("search_code", {"keyword": "dangerous_call"})
    assert search_route is not None
    assert search_route.adapter_name == "code_index"
    assert search_route.mcp_tool_name == "search_code_advanced"

    extract_route = router.route(
        "extract_function",
        {"file_path": "src/time64.c", "function_name": "asctime64_r"},
    )
    assert extract_route is not None
    assert extract_route.adapter_name == "code_index"
    assert extract_route.mcp_tool_name == "get_symbol_body"

    assert router.route("edit_file", {"file_path": "src/main.py"}) is None
    assert router.route("qmd_query", {"query": "auth"}) is None
    assert router.route("sequential_thinking", {"goal": "plan"}) is None
    assert router.route("skill_lookup", {"query": "scan"}) is None


@pytest.mark.asyncio
async def test_agent_does_not_fallback_to_local_read_tool_when_mcp_is_unavailable(tmp_path):
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={
            "filesystem": FastMCPStdioAdapter(
                command="__missing_stdio_binary__",
                args=[],
                cwd=str(tmp_path),
                timeout=5,
                runtime_domain="stdio",
            )
        },
        runtime_modes={"filesystem": "stdio_only"},
        default_runtime_mode="stdio_only",
        project_root=str(tmp_path),
        strict_mode=True,
    )
    local_tool = _LocalReadTool()
    agent = _make_agent(tools={"read_file": local_tool}, runtime=runtime)

    output = await agent.execute_tool("read_file", {"file_path": "src/main.py"})

    assert "mcp_adapter_unavailable:filesystem" in output
    assert local_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_probe_runtime_prefers_list_allowed_directories_for_filesystem(tmp_path):
    filesystem_adapter = _ProbeAdapter(
        tools=[
            {"name": "get_file_info", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
            {"name": "read_file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
            {"name": "list_allowed_directories", "inputSchema": {"type": "object", "properties": {}}},
        ],
        call_result=lambda tool_name, arguments: {
            "success": True,
            "data": {"allowedDirectories": [str(tmp_path)]} if tool_name == "list_allowed_directories" else "ok",
            "metadata": {},
        },
    )
    code_index_adapter = _ProbeAdapter(
        tools=[
            {"name": "get_file_summary", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "number"}}}},
        ],
        call_result={"success": True, "data": "ok", "metadata": {}},
    )
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter, "code_index": code_index_adapter},
        runtime_modes={"filesystem": "stdio_only", "code_index": "stdio_only"},
        required_mcps=["filesystem", "code_index"],
        default_runtime_mode="stdio_only",
        strict_mode=True,
        project_root=str(tmp_path),
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="stdio")

    assert probe["ready"] is True
    assert probe["details"]["filesystem"]["selected_tool"] == "list_allowed_directories"
    assert filesystem_adapter.calls[0][0] == "list_allowed_directories"


@pytest.mark.asyncio
async def test_probe_runtime_accepts_stringified_allowed_directories_payload(tmp_path):
    stringified_payload = (
        "CallToolResult(content=[TextContent(type='text', text='Allowed directories:\n"
        + str(tmp_path)
        + "', annotations=None, meta=None)], structured_content={'content': 'Allowed directories:\n"
        + str(tmp_path)
        + "'}, meta=None, data=Root(content='Allowed directories:\n"
        + str(tmp_path)
        + "'), is_error=False)"
    )
    filesystem_adapter = _ProbeAdapter(
        tools=[
            {"name": "list_allowed_directories", "inputSchema": {"type": "object", "properties": {}}},
        ],
        call_result={"success": True, "data": stringified_payload, "metadata": {}},
    )
    code_index_adapter = _ProbeAdapter(
        tools=[
            {"name": "get_file_summary", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "number"}}}},
        ],
        call_result={"success": True, "data": "ok", "metadata": {}},
    )
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter, "code_index": code_index_adapter},
        runtime_modes={"filesystem": "stdio_only", "code_index": "stdio_only"},
        required_mcps=["filesystem", "code_index"],
        default_runtime_mode="stdio_only",
        strict_mode=True,
        project_root=str(tmp_path),
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="stdio")

    assert probe["ready"] is True
    assert probe["details"]["filesystem"]["selected_tool"] == "list_allowed_directories"
    assert probe["details"]["filesystem"]["allowed_directories"] == [str(tmp_path)]


@pytest.mark.asyncio
async def test_probe_runtime_classifies_filesystem_allowed_dir_failure(tmp_path):
    raw_error = f"Access denied - path outside allowed directories: {tmp_path}/tmp/.mcp_required_media_probe.png not in"
    filesystem_adapter = _ProbeAdapter(
        tools=[
            {"name": "read_file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        ],
        call_result={"success": False, "error": raw_error, "metadata": {}},
    )
    code_index_adapter = _ProbeAdapter(
        tools=[
            {"name": "get_file_summary", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "number"}}}},
        ],
        call_result={"success": True, "data": "ok", "metadata": {}},
    )
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter, "code_index": code_index_adapter},
        runtime_modes={"filesystem": "stdio_only", "code_index": "stdio_only"},
        required_mcps=["filesystem", "code_index"],
        default_runtime_mode="stdio_only",
        strict_mode=True,
        project_root=str(tmp_path),
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="stdio")

    assert probe["ready"] is False
    assert probe["not_ready"][0]["reason"] == "filesystem_project_root_not_allowed"
    assert probe["details"]["filesystem"]["reason_class"] == "filesystem_project_root_not_allowed"
    assert probe["details"]["filesystem"]["project_root"] == str(tmp_path)
    assert str(tmp_path) in str(probe["details"]["filesystem"]["probe_path"])
