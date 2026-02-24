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
    assert arguments.get("collections")
    assert arguments["collections"][0].startswith("project_")


def test_qmd_router_normalizes_query_shorthand():
    router = MCPToolRouter()
    route = router.route("qmd_query", {"query": "time64 overflow"})

    assert route is not None
    assert route.adapter_name == "qmd"
    assert route.mcp_tool_name == "query"
    searches = route.arguments.get("searches")
    assert isinstance(searches, list)
    assert searches[0]["query"] == "time64 overflow"
