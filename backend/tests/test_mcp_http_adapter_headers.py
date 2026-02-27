import pytest

from app.services.agent.mcp.runtime import FastMCPHttpAdapter


@pytest.mark.asyncio
async def test_http_adapter_uses_streamable_transport_with_headers(monkeypatch):
    captured = {}

    class _DummyTransport:
        def __init__(self, url, headers=None, auth=None, sse_read_timeout=None, httpx_client_factory=None):
            captured["transport_url"] = str(url)
            captured["transport_headers"] = headers

    class _DummyClient:
        def __init__(self, transport=None, timeout=None):
            captured["client_transport"] = transport
            captured["client_timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def call_tool(self, tool_name, arguments):
            captured["tool_name"] = tool_name
            captured["tool_arguments"] = dict(arguments or {})
            return {"success": True, "data": "ok"}

    monkeypatch.setattr("app.services.agent.mcp.runtime.StreamableHttpTransport", _DummyTransport)
    monkeypatch.setattr("app.services.agent.mcp.runtime.MCPClient", _DummyClient)

    adapter = FastMCPHttpAdapter(
        url="http://127.0.0.1:8765/mcp",
        timeout=30,
        runtime_domain="backend",
        headers={"Mcp-Project-Path": "/tmp/project"},
    )

    result = await adapter.call_tool("search_code_advanced", {"pattern": "sprintf"})

    assert result["success"] is True
    assert captured["transport_url"] == "http://127.0.0.1:8765/mcp"
    assert captured["transport_headers"] == {"Mcp-Project-Path": "/tmp/project"}
    assert captured["tool_name"] == "search_code_advanced"
    assert captured["tool_arguments"] == {"pattern": "sprintf"}
