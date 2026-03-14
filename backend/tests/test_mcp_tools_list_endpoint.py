from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import (
    MCPVerifyRequest,
    MCPToolsCallRequest,
    MCPToolsListRequest,
    verify_mcp_runtime,
    call_mcp_tool_runtime,
    list_mcp_tools_runtime,
)
from app.services.agent.mcp.runtime import MCPExecutionResult


class _FakeExecuteResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    async def execute(self, *args, **kwargs):
        return _FakeExecuteResult()


class _FakeRuntime:
    def __init__(self, payload_by_mcp, call_payload=None):
        self.payload_by_mcp = payload_by_mcp
        self.call_payload = call_payload or MCPExecutionResult(
            handled=True,
            success=True,
            data="ok",
            metadata={"mcp_runtime_domain": "backend"},
        )
        self.calls = []
        self.call_invocations = []

    async def list_mcp_tools(self, mcp_name: str):
        key = str(mcp_name or "").strip().lower()
        self.calls.append(key)
        return dict(self.payload_by_mcp.get(key) or {})

    async def call_mcp_tool(self, *, mcp_name: str, tool_name: str, arguments, agent_name=None, alias_used=None):
        self.call_invocations.append(
            {
                "mcp_name": mcp_name,
                "tool_name": tool_name,
                "arguments": dict(arguments or {}),
                "agent_name": agent_name,
                "alias_used": alias_used,
            }
        )
        return self.call_payload


def _setup_common(monkeypatch, runtime, *, catalog):
    monkeypatch.setattr(
        config_module,
        "get_default_config",
        lambda: {"otherConfig": {"mcpConfig": {"catalog": catalog}}},
    )
    monkeypatch.setattr(
        config_module,
        "_sanitize_other_config",
        lambda raw: {"mcpConfig": {"catalog": catalog}},
    )

    def _fake_build_task_mcp_runtime(*, active_mcp_ids, **kwargs):
        return runtime

    monkeypatch.setattr(agent_tasks_module, "_build_task_mcp_runtime", _fake_build_task_mcp_runtime)


@pytest.mark.asyncio
async def test_list_mcp_tools_returns_empty_when_catalog_has_no_active_mcps(monkeypatch):
    catalog = []
    runtime = _FakeRuntime({})
    _setup_common(monkeypatch, runtime, catalog=catalog)

    response = await list_mcp_tools_runtime(
        MCPToolsListRequest(),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.results == []
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_list_mcp_tools_rejects_removed_filesystem(monkeypatch):
    catalog = []
    runtime = _FakeRuntime({})
    _setup_common(monkeypatch, runtime, catalog=catalog)

    with pytest.raises(HTTPException) as excinfo:
        await list_mcp_tools_runtime(
            MCPToolsListRequest(mcp_ids=["filesystem"], include_internal=True),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_list_mcp_tools_rejects_removed_code_index(monkeypatch):
    catalog = []
    runtime = _FakeRuntime({})
    _setup_common(monkeypatch, runtime, catalog=catalog)

    with pytest.raises(HTTPException) as excinfo:
        await list_mcp_tools_runtime(
            MCPToolsListRequest(mcp_ids=["filesystem", "code_index"]),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_call_mcp_tool_runtime_returns_unified_payload(monkeypatch):
    catalog = []
    call_payload = MCPExecutionResult(
        handled=True,
        success=True,
        data="probe-ok",
        metadata={"mcp_runtime_domain": "sandbox", "mcp_used": True},
    )
    runtime = _FakeRuntime({}, call_payload=call_payload)
    _setup_common(monkeypatch, runtime, catalog=catalog)

    with pytest.raises(HTTPException) as excinfo:
        await call_mcp_tool_runtime(
            MCPToolsCallRequest(
                mcp_id="filesystem",
                tool_name="list_directory",
                arguments={"path": "."},
            ),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_call_mcp_tool_runtime_blocks_internal_tool_by_default(monkeypatch):
    catalog = []
    runtime = _FakeRuntime({})
    _setup_common(monkeypatch, runtime, catalog=catalog)

    with pytest.raises(HTTPException) as excinfo:
        await call_mcp_tool_runtime(
            MCPToolsCallRequest(
                mcp_id="filesystem",
                tool_name="set_project_path",
                arguments={"path": "."},
            ),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )
    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_call_mcp_tool_runtime_rejects_removed_code_index(monkeypatch):
    catalog = []
    runtime = _FakeRuntime({})
    _setup_common(monkeypatch, runtime, catalog=catalog)

    with pytest.raises(HTTPException) as excinfo:
        await call_mcp_tool_runtime(
            MCPToolsCallRequest(
                mcp_id="code_index",
                tool_name="list_directory",
                arguments={"path": "."},
            ),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_verify_mcp_runtime_rejects_removed_code_index(monkeypatch):
    _setup_common(monkeypatch, _FakeRuntime({}), catalog=[])

    with pytest.raises(HTTPException) as excinfo:
        await verify_mcp_runtime(
            MCPVerifyRequest(mcp_id="code_index"),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_verify_mcp_runtime_rejects_removed_filesystem(monkeypatch):
    _setup_common(monkeypatch, _FakeRuntime({}), catalog=[])

    with pytest.raises(HTTPException) as excinfo:
        await verify_mcp_runtime(
            MCPVerifyRequest(mcp_id="filesystem"),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert excinfo.value.status_code == 400
    assert "不支持的 MCP" in str(excinfo.value.detail)
