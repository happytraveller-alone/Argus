import pytest

from app.services.agent.mcp.qmd_index import QmdEnsureResult, QmdLazyIndexAdapter
from app.services.agent.mcp.router import MCPToolRouter


class _CaptureAdapter:
    def __init__(self):
        self.runtime_domain = "backend"
        self.calls = []

    def is_available(self) -> bool:
        return True

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return {"success": True, "data": {"tool_name": tool_name, "arguments": arguments}}


class _ToolObj:
    def __init__(self, name: str):
        self.name = name
        self.description = ""
        self.inputSchema = {"type": "object", "properties": {}}


@pytest.mark.asyncio
async def test_qmd_lazy_adapter_injects_collection_and_keeps_query_available(tmp_path, monkeypatch):
    base_adapter = _CaptureAdapter()
    adapter = QmdLazyIndexAdapter(
        adapter=base_adapter,
        project_root=str(tmp_path),
        project_id="proj-1",
        lazy_enabled=True,
    )

    monkeypatch.setattr(adapter, "_ensure_collection_sync", lambda: QmdEnsureResult(ok=True))

    result = await adapter.call_tool(
        "query",
        {"searches": [{"type": "vec", "query": "asctime64_r"}]},
    )

    assert result["success"] is True
    assert len(base_adapter.calls) == 1
    _, arguments = base_adapter.calls[0]
    assert arguments.get("collection")
    assert str(arguments["collection"]).startswith("project_")


@pytest.mark.asyncio
async def test_qmd_lazy_adapter_list_tools_normalizes_model_objects(tmp_path):
    class _ToolAdapter(_CaptureAdapter):
        async def list_tools(self):
            return [_ToolObj("search"), _ToolObj("status")]

    adapter = QmdLazyIndexAdapter(
        adapter=_ToolAdapter(),
        project_root=str(tmp_path),
        project_id="proj-1",
        lazy_enabled=False,
    )

    tools = await adapter.list_tools()
    assert [item.get("name") for item in tools] == ["search", "status"]


def test_qmd_router_normalizes_query_shorthand():
    router = MCPToolRouter()
    route = router.route("qmd_query", {"query": "time64 overflow"})

    assert route is not None
    assert route.adapter_name == "qmd"
    assert route.mcp_tool_name == "deep_search"
    searches = route.arguments.get("searches")
    assert isinstance(searches, list)
    assert searches[0]["query"] == "time64 overflow"
    assert route.arguments.get("query") == "time64 overflow"


def test_router_normalizes_list_files_directory_to_path():
    router = MCPToolRouter()
    route = router.route("list_files", {"directory": ".", "recursive": False})

    assert route is not None
    assert route.adapter_name == "code_index"
    assert route.mcp_tool_name == "find_files"
    assert route.arguments.get("path") == "."
    assert route.arguments.get("directory") == "."


def test_router_normalizes_search_code_pattern_and_glob():
    router = MCPToolRouter()
    route = router.route("search_code", {"keyword": "sprintf", "file_pattern": "src/*.c"})

    assert route is not None
    assert route.adapter_name == "code_index"
    assert route.mcp_tool_name == "search_code_advanced"
    assert route.arguments.get("pattern") == "sprintf"
    assert route.arguments.get("glob") == "src/*.c"
