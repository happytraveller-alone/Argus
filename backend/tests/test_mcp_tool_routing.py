import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime, _probe_required_mcp_runtime
from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.mcp import FastMCPStdioAdapter, MCPRuntime, MCPToolRouter


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _CodeWindowSchema(BaseModel):
    file_path: str
    anchor_line: int


class _SearchSchema(BaseModel):
    keyword: str


class _LocalCodeWindowTool:
    args_schema = _CodeWindowSchema
    name = "get_code_window"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(
            success=True,
            data=f"local-code-window:{kwargs.get('file_path')}:{kwargs.get('anchor_line')}",
            error=None,
            metadata={"file_path": kwargs.get("file_path"), "anchor_line": kwargs.get("anchor_line")},
        )


class _LocalSearchTool:
    args_schema = _SearchSchema
    name = "search_code"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(
            success=True,
            data=f"local-search:{kwargs.get('keyword')}",
            error=None,
            metadata={"keyword": kwargs.get("keyword")},
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
    trace_dir = Path(tempfile.mkdtemp(prefix="agent-trace-"))
    trace_path = trace_dir / "test-agent.log"
    with patch.object(BaseAgent, "_resolve_trace_log_path", return_value=str(trace_path)):
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
async def test_task_mcp_runtime_does_not_register_filesystem_adapters(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=[],
    )

    assert isinstance(runtime, MCPRuntime)
    assert runtime.adapters == {}
    assert runtime.domain_adapters == {}
    assert runtime.default_runtime_mode == "stdio_only"
    assert runtime.runtime_modes == {}
    assert runtime.required_mcps == []


@pytest.mark.asyncio
async def test_task_mcp_runtime_keeps_project_root_without_filesystem_stdio_args(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=[],
    )

    assert runtime.project_root == str(tmp_path)
    assert runtime.adapters == {}


def test_mcp_router_exposes_local_scan_core_routes():
    router = MCPToolRouter()

    assert router.route("read_file", {"file_path": "src/main.py"}) is None

    search_route = router.route("search_code", {"keyword": "dangerous_call"})
    assert search_route is not None
    assert search_route.adapter_name == "__local__"
    assert search_route.mcp_tool_name == "search_code"
    assert search_route.arguments["pattern"] == "dangerous_call"
    assert search_route.arguments["regex"] is False
    assert "query" not in search_route.arguments

    regex_search_route = router.route(
        "search_code",
        {"keyword": r"foo\\s*\\(", "is_regex": True},
    )
    assert regex_search_route is not None
    assert regex_search_route.arguments["pattern"] == r"foo\\s*\\("
    assert regex_search_route.arguments["regex"] is True
    assert "query" not in regex_search_route.arguments

    query_search_route = router.route("search_code", {"query": "danger"})
    assert query_search_route is not None
    assert query_search_route.arguments["pattern"] == "danger"
    assert query_search_route.arguments["regex"] is False
    assert "query" not in query_search_route.arguments

    scoped_search_route = router.route(
        "search_code",
        {"keyword": "danger", "directory": "src", "glob": "*.py"},
    )
    assert scoped_search_route is not None
    assert scoped_search_route.arguments["file_pattern"] == "src/**/*.py"
    assert "glob" not in scoped_search_route.arguments
    assert "directory" not in scoped_search_route.arguments

    directory_only_search_route = router.route(
        "search_code",
        {"keyword": "danger", "directory": "src"},
    )
    assert directory_only_search_route is not None
    assert directory_only_search_route.arguments["file_pattern"] == "src/**"
    assert "directory" not in directory_only_search_route.arguments

    code_window_route = router.route(
        "get_code_window",
        {"file_path": "src/time64.c", "anchor_line": 22, "before_lines": 2, "after_lines": 3},
    )
    assert code_window_route is not None
    assert code_window_route.adapter_name == "__local__"
    assert code_window_route.mcp_tool_name == "get_code_window"
    assert code_window_route.arguments["file_path"] == "src/time64.c"
    assert code_window_route.arguments["anchor_line"] == 22

    locate_route = router.route(
        "locate_enclosing_function",
        {"file_path": "src/time64.c", "line_start": 22},
    )
    assert locate_route is not None
    assert locate_route.adapter_name == "__local__"
    assert locate_route.mcp_tool_name == "locate_enclosing_function"
    assert locate_route.arguments["file_path"] == "src/time64.c"
    assert locate_route.arguments["line"] == 22

    locate_embedded_line_route = router.route(
        "locate_enclosing_function",
        {"path": "src/time64.c:8", "line": 7, "line_start": 22},
    )
    assert locate_embedded_line_route is not None
    assert locate_embedded_line_route.arguments["file_path"] == "src/time64.c"
    assert locate_embedded_line_route.arguments["line"] == 22

    assert router.route("edit_file", {"file_path": "src/main.py"}) is None
    assert router.route("qmd_query", {"query": "auth"}) is None
    assert router.route("sequential_thinking", {"goal": "plan"}) is None
    assert router.route("skill_lookup", {"query": "scan"}) is None


@pytest.mark.asyncio
async def test_agent_ignores_unavailable_filesystem_adapter_for_local_read_tool(tmp_path):
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
    local_tool = _LocalCodeWindowTool()
    agent = _make_agent(tools={"get_code_window": local_tool}, runtime=runtime)

    output = await agent.execute_tool("get_code_window", {"file_path": "src/main.py", "anchor_line": 8})

    assert "local-code-window:src/main.py:8" in output
    assert local_tool.execute_calls == 1


@pytest.mark.asyncio
async def test_agent_rejects_legacy_read_file_when_strict_mode_route_is_missing(tmp_path):
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        runtime_modes={},
        default_runtime_mode="stdio_only",
        project_root=str(tmp_path),
        strict_mode=True,
    )
    local_tool = _LocalCodeWindowTool()
    agent = _make_agent(tools={"get_code_window": local_tool}, runtime=runtime)

    output = await agent.execute_tool("read_file", {"file_path": "src/main.py"})

    assert "工具 'read_file' 不存在" in output or "已下线" in output
    assert local_tool.execute_calls == 0


@pytest.mark.asyncio
async def test_agent_runs_local_search_code_when_strict_mode_route_is_local_only(tmp_path):
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={},
        runtime_modes={},
        default_runtime_mode="stdio_only",
        project_root=str(tmp_path),
        strict_mode=True,
    )
    local_tool = _LocalSearchTool()
    agent = _make_agent(tools={"search_code": local_tool}, runtime=runtime)
    agent.config.metadata.update({"smart_audit_mode": True})

    output = await agent.execute_tool("search_code", {"keyword": "dangerous_call"})

    assert output == "local-search:dangerous_call"
    assert local_tool.execute_calls == 1


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
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter},
        runtime_modes={"filesystem": "stdio_only"},
        required_mcps=["filesystem"],
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
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter},
        runtime_modes={"filesystem": "stdio_only"},
        required_mcps=["filesystem"],
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
    runtime = MCPRuntime(
        enabled=True,
        prefer_mcp=True,
        adapters={"filesystem": filesystem_adapter},
        runtime_modes={"filesystem": "stdio_only"},
        required_mcps=["filesystem"],
        default_runtime_mode="stdio_only",
        strict_mode=True,
        project_root=str(tmp_path),
    )

    probe = await _probe_required_mcp_runtime(runtime, runtime_domain="stdio")

    assert probe["ready"] is False
    assert probe["not_ready"][0]["reason"] == "filesystem_project_root_not_allowed"
    assert probe["details"]["filesystem"]["reason_class"] == "filesystem_project_root_not_allowed"
    assert probe["details"]["filesystem"]["project_root"] == str(tmp_path)
