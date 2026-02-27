import pytest

from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime
from app.core.config import settings
from app.services.agent.mcp.runtime import FastMCPHttpAdapter, FastMCPStdioAdapter, MCPRuntime


class _AlwaysFailAdapter:
    runtime_domain = "backend"

    def is_available(self) -> bool:
        return True

    async def call_tool(self, tool_name, arguments):
        raise FileNotFoundError("No such file or directory")


class _DisconnectFailAdapter:
    runtime_domain = "backend"

    def is_available(self) -> bool:
        return True

    async def call_tool(self, tool_name, arguments):
        raise RuntimeError("Server disconnected without sending a response.")


class _HealthResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _HealthyHttpClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _HealthResponse(200)


class _UnhealthyHttpClient(_HealthyHttpClient):
    def get(self, url, headers=None):
        return _HealthResponse(503)


class _TcpOnlySocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ProjectPathBootstrapClient:
    calls = []

    def __init__(self, transport=None, timeout=None):
        self.transport = transport
        self.timeout = timeout
        self.project_ready = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def call_tool(self, tool_name, arguments):
        self.__class__.calls.append((tool_name, dict(arguments or {})))
        if tool_name == "set_project_path":
            if arguments.get("path") == "/tmp/project":
                self.project_ready = True
                return {"success": True, "data": "ok"}
            return {"success": False, "error": "invalid_arguments"}
        if tool_name == "search_code_advanced":
            if not self.project_ready:
                raise RuntimeError(
                    "Operation failed: Project path not set. "
                    "Please use set_project_path to set a project directory first."
                )
            return {"success": True, "data": "search-ok"}
        return {"success": True, "data": "noop"}


class _HttpFallbackMCPClient:
    calls = []

    def __init__(self, endpoint, timeout=None):
        self.endpoint = endpoint
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def call_tool(self, tool_name, arguments):
        self.__class__.calls.append((self.endpoint, tool_name, dict(arguments or {})))
        if str(self.endpoint).rstrip("/").endswith("/mcp"):
            raise RuntimeError("Client failed to connect: Server disconnected without sending a response.")
        return {"success": True, "data": f"ok:{tool_name}"}


class _HttpProjectPathBootstrapClient:
    calls = []

    def __init__(self, transport=None, timeout=None):
        self.transport = transport
        self.timeout = timeout
        self.project_ready = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def call_tool(self, tool_name, arguments):
        self.__class__.calls.append((tool_name, dict(arguments or {})))
        if tool_name == "set_project_path":
            if arguments.get("path") == "/tmp/project":
                self.project_ready = True
                return {"success": True, "data": "ok"}
            return {"success": False, "error": "invalid_arguments"}
        if tool_name == "search_code_advanced":
            if not self.project_ready:
                raise RuntimeError(
                    "Operation failed: Project path not set. "
                    "Please use set_project_path to set a project directory first."
                )
            return {"success": True, "data": "search-ok"}
        return {"success": True, "data": "noop"}


class _ListToolItem:
    def __init__(self, name: str, description: str = "", input_schema=None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema if isinstance(input_schema, dict) else {}


class _StdioListToolsClient:
    def __init__(self, transport=None, timeout=None):
        self.transport = transport
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def list_tools(self):
        return [
            _ListToolItem("read_file", "Read file", {"type": "object"}),
            {"name": "write_file", "description": "Write file", "inputSchema": {"type": "object"}},
            {"id": "list_directory", "description": "List", "input_schema": {"type": "object"}},
        ]


class _HttpListToolsClient:
    def __init__(self, transport=None, timeout=None):
        self.transport = transport
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def list_tools(self):
        return [{"name": "query", "description": "Query", "inputSchema": {"type": "object"}}]


class _HttpListToolsFailClient(_HttpListToolsClient):
    async def list_tools(self):
        raise RuntimeError("Server disconnected without sending a response.")


class _AsyncJsonResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _AsyncJsonRpcClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        return _AsyncJsonResponse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {
                            "name": "status",
                            "description": "status tool",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            }
        )


class _HttpCall400Client(_HttpListToolsClient):
    async def call_tool(self, tool_name, arguments):
        raise RuntimeError(
            "Client error '400 Bad Request' for url 'http://127.0.0.1:8765/mcp'"
        )


class _AsyncJsonRpcToolClient(_AsyncJsonRpcClient):
    async def post(self, url, json=None, headers=None):
        if isinstance(json, dict) and str(json.get("method")) == "tools/call":
            return _AsyncJsonResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "success": True,
                        "data": {"ok": True},
                    },
                }
            )
        return await super().post(url, json=json, headers=headers)


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


def test_fastmcp_stdio_adapter_prefers_local_filesystem_binary_for_npx(monkeypatch):
    def _which(name: str):
        mapping = {
            "npx": "/usr/bin/npx",
            "mcp-server-filesystem": "/usr/local/bin/mcp-server-filesystem",
        }
        return mapping.get(name)

    monkeypatch.setattr("app.services.agent.mcp.runtime.shutil.which", _which)
    adapter = FastMCPStdioAdapter(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp/project-root"],
    )

    assert adapter.command == "/usr/local/bin/mcp-server-filesystem"
    assert adapter.args == ["/tmp/project-root"]


def test_fastmcp_stdio_adapter_keeps_npx_when_local_binary_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.runtime.shutil.which",
        lambda name: "/usr/bin/npx" if name == "npx" else None,
    )
    adapter = FastMCPStdioAdapter(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp/project-root"],
    )

    assert adapter.command == "npx"
    assert adapter.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/project-root"]


def test_fastmcp_stdio_adapter_prefers_local_sequential_binary_for_npm_exec(monkeypatch):
    def _which(name: str):
        mapping = {
            "npm": "/usr/bin/npm",
            "mcp-server-sequential-thinking": "/usr/local/bin/mcp-server-sequential-thinking",
        }
        return mapping.get(name)

    monkeypatch.setattr("app.services.agent.mcp.runtime.shutil.which", _which)
    adapter = FastMCPStdioAdapter(
        command="npm",
        args=["exec", "-y", "@modelcontextprotocol/server-sequential-thinking", "--"],
    )

    assert adapter.command == "/usr/local/bin/mcp-server-sequential-thinking"
    assert adapter.args == []


@pytest.mark.asyncio
async def test_fastmcp_stdio_adapter_bootstraps_project_path_then_retries(monkeypatch):
    _ProjectPathBootstrapClient.calls.clear()

    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _ProjectPathBootstrapClient)
    adapter = FastMCPStdioAdapter(command="dummy", cwd="/tmp/project")
    monkeypatch.setattr(adapter, "_build_transport", lambda: object())

    result = await adapter.call_tool("search_code_advanced", {"pattern": "plist_from_"})

    assert result.get("success") is True
    assert result.get("data") == "search-ok"
    tool_names = [name for name, _ in _ProjectPathBootstrapClient.calls]
    assert "set_project_path" in tool_names
    assert tool_names.count("search_code_advanced") >= 2


@pytest.mark.asyncio
async def test_fastmcp_stdio_adapter_bootstrap_needs_project_root(monkeypatch):
    _ProjectPathBootstrapClient.calls.clear()

    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _ProjectPathBootstrapClient)
    adapter = FastMCPStdioAdapter(command="dummy", cwd=None)
    monkeypatch.setattr(adapter, "_build_transport", lambda: object())

    with pytest.raises(RuntimeError):
        await adapter.call_tool("search_code_advanced", {"pattern": "plist_from_"})


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


def test_fastmcp_http_adapter_checks_health_endpoint(monkeypatch):
    monkeypatch.setattr("app.services.agent.mcp.runtime.httpx.Client", _HealthyHttpClient)
    adapter = FastMCPHttpAdapter(url="http://codebadger-mcp:4242/mcp")
    assert adapter.is_available() is True
    assert adapter.availability_reason is None


def test_fastmcp_http_adapter_reports_healthcheck_failure(monkeypatch):
    monkeypatch.setattr("app.services.agent.mcp.runtime.httpx.Client", _UnhealthyHttpClient)
    adapter = FastMCPHttpAdapter(url="http://codebadger-mcp:4242/mcp")
    assert adapter.is_available() is False
    assert "healthcheck_failed:status_503" in str(adapter.availability_reason or "")


def test_fastmcp_http_adapter_remote_protocol_falls_back_to_tcp(monkeypatch):
    import httpx

    class _RemoteProtocolErrorClient(_HealthyHttpClient):
        def get(self, url, headers=None):
            raise httpx.RemoteProtocolError("server disconnected")

    monkeypatch.setattr("app.services.agent.mcp.runtime.httpx.Client", _RemoteProtocolErrorClient)
    monkeypatch.setattr(
        "app.services.agent.mcp.runtime.socket.create_connection",
        lambda *args, **kwargs: _TcpOnlySocket(),
    )

    adapter = FastMCPHttpAdapter(url="http://codebadger-mcp:4242/mcp")
    assert adapter.is_available() is True
    assert adapter.availability_reason is None


@pytest.mark.asyncio
async def test_runtime_disconnect_error_trips_circuit_breaker():
    runtime = MCPRuntime(
        enabled=True,
        adapters={"filesystem": _DisconnectFailAdapter()},
        adapter_failure_threshold=2,
    )

    for _ in range(2):
        await runtime.execute_tool(
            tool_name="read_file",
            tool_input={"file_path": "src/a.c"},
        )

    assert runtime.can_handle("read_file") is False


@pytest.mark.asyncio
async def test_fastmcp_http_adapter_fallbacks_to_alternate_endpoint_when_mcp_disconnects(monkeypatch):
    _HttpFallbackMCPClient.calls.clear()
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _HttpFallbackMCPClient)

    adapter = FastMCPHttpAdapter(url="http://codebadger-mcp:4242/mcp")
    result = await adapter.call_tool("cpg_query", {"query": "startup_probe"})

    assert result.get("success") is True
    called_endpoints = [item[0] for item in _HttpFallbackMCPClient.calls]
    assert called_endpoints[0].endswith("/mcp")
    assert any(endpoint.rstrip("/") == "http://codebadger-mcp:4242" for endpoint in called_endpoints[1:])


@pytest.mark.asyncio
async def test_fastmcp_http_adapter_bootstraps_project_path_for_code_index(monkeypatch):
    _HttpProjectPathBootstrapClient.calls.clear()
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _HttpProjectPathBootstrapClient)

    adapter = FastMCPHttpAdapter(
        url="http://127.0.0.1:8765/mcp",
        headers={"Mcp-Project-Path": "/tmp/project"},
    )
    result = await adapter.call_tool("search_code_advanced", {"pattern": "plist_from_", "max_results": 1})

    assert result.get("success") is True
    assert result.get("data") == "search-ok"
    tool_names = [name for name, _ in _HttpProjectPathBootstrapClient.calls]
    assert "set_project_path" in tool_names
    assert tool_names.count("search_code_advanced") >= 2


@pytest.mark.asyncio
async def test_fastmcp_stdio_adapter_list_tools_normalizes_payload(monkeypatch):
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _StdioListToolsClient)
    adapter = FastMCPStdioAdapter(command="dummy", cwd="/tmp/project")
    monkeypatch.setattr(adapter, "_build_transport", lambda: object())

    tools = await adapter.list_tools()

    assert [item["name"] for item in tools] == ["read_file", "write_file", "list_directory"]
    assert all(isinstance(item.get("inputSchema"), dict) for item in tools)


@pytest.mark.asyncio
async def test_fastmcp_http_adapter_list_tools_uses_streamable_transport(monkeypatch):
    class _DummyTransport:
        def __init__(self, url, headers=None, auth=None, sse_read_timeout=None, httpx_client_factory=None):
            self.url = url
            self.headers = headers

    monkeypatch.setattr("app.services.agent.mcp.runtime.StreamableHttpTransport", _DummyTransport)
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _HttpListToolsClient)

    adapter = FastMCPHttpAdapter(url="http://127.0.0.1:8765/mcp", headers={"X-Test": "1"})
    tools = await adapter.list_tools()

    assert tools == [{"name": "query", "description": "Query", "inputSchema": {"type": "object"}}]


@pytest.mark.asyncio
async def test_fastmcp_http_adapter_list_tools_falls_back_to_json_rpc(monkeypatch):
    class _DummyTransport:
        def __init__(self, url, headers=None, auth=None, sse_read_timeout=None, httpx_client_factory=None):
            self.url = url
            self.headers = headers

    monkeypatch.setattr("app.services.agent.mcp.runtime.StreamableHttpTransport", _DummyTransport)
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _HttpListToolsFailClient)
    monkeypatch.setattr("app.services.agent.mcp.runtime.httpx.AsyncClient", _AsyncJsonRpcClient)

    adapter = FastMCPHttpAdapter(url="http://127.0.0.1:8765/mcp")
    tools = await adapter.list_tools()

    assert tools == [{"name": "status", "description": "status tool", "inputSchema": {"type": "object"}}]


@pytest.mark.asyncio
async def test_fastmcp_http_adapter_call_tool_falls_back_to_json_rpc_after_400(monkeypatch):
    class _DummyTransport:
        def __init__(self, url, headers=None, auth=None, sse_read_timeout=None, httpx_client_factory=None):
            self.url = url
            self.headers = headers

    monkeypatch.setattr("app.services.agent.mcp.runtime.StreamableHttpTransport", _DummyTransport)
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _HttpCall400Client)
    monkeypatch.setattr("app.services.agent.mcp.runtime.httpx.AsyncClient", _AsyncJsonRpcToolClient)

    adapter = FastMCPHttpAdapter(url="http://127.0.0.1:8765/mcp")
    payload = await adapter.call_tool("status", {})

    assert payload.get("success") is True


def test_qmd_http_unavailable_can_fallback_to_stdio(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_QMD_SANDBOX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_BACKEND_URL", "http://localhost:8181/mcp")
    monkeypatch.setattr(settings, "MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr(
        "app.services.agent.mcp.runtime.FastMCPHttpAdapter.is_available",
        lambda self: False,
    )

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
        prefer_stdio_when_http_unavailable=True,
        active_mcp_ids=["qmd"],
    )
    qmd_adapter = runtime.domain_adapters["qmd"]["backend"]
    inner = getattr(qmd_adapter, "_adapter", None)
    assert isinstance(inner, FastMCPStdioAdapter)
