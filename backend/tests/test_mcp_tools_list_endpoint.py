from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import (
    MCPToolsListRequest,
    list_mcp_tools_runtime,
)


class _FakeExecuteResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    async def execute(self, *args, **kwargs):
        return _FakeExecuteResult()


class _FakeRuntime:
    def __init__(self, payload_by_mcp):
        self.payload_by_mcp = payload_by_mcp
        self.calls = []

    async def list_mcp_tools(self, mcp_name: str):
        key = str(mcp_name or "").strip().lower()
        self.calls.append(key)
        return dict(self.payload_by_mcp.get(key) or {})


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
async def test_list_mcp_tools_filters_internal_tools_by_default(monkeypatch):
    catalog = [
        {"id": "filesystem", "type": "mcp-server"},
        {"id": "code_index", "type": "mcp-server"},
        {"id": "skill-pack-demo", "type": "skill-pack"},
    ]
    runtime = _FakeRuntime(
        {
            "filesystem": {
                "success": True,
                "tools": [
                    {"name": "set_project_path", "description": "internal", "inputSchema": {}},
                    {"name": "list_directory", "description": "list", "inputSchema": {}},
                ],
                "metadata": {"mcp_runtime_domain": "sandbox"},
            },
            "code_index": {
                "success": True,
                "tools": [
                    {"name": "search_code_advanced", "description": "search", "inputSchema": {}},
                ],
                "metadata": {"mcp_runtime_domain": "backend"},
            },
        }
    )
    _setup_common(monkeypatch, runtime, catalog=catalog)

    response = await list_mcp_tools_runtime(
        MCPToolsListRequest(),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.mcp_id for item in response.results] == ["filesystem", "code_index"]
    assert runtime.calls == ["filesystem", "code_index"]

    filesystem = response.results[0]
    assert filesystem.success is True
    assert filesystem.runtime_domain == "sandbox"
    assert filesystem.listed_count == 2
    assert filesystem.visible_count == 1
    assert [tool.name for tool in filesystem.tools] == ["list_directory"]


@pytest.mark.asyncio
async def test_list_mcp_tools_can_include_internal_tools(monkeypatch):
    catalog = [{"id": "filesystem", "type": "mcp-server"}]
    runtime = _FakeRuntime(
        {
            "filesystem": {
                "success": True,
                "tools": [
                    {"name": "set_project_path", "description": "internal", "inputSchema": {}},
                    {"name": "list_directory", "description": "list", "inputSchema": {}},
                ],
                "metadata": {"mcp_runtime_domain": "sandbox"},
            }
        }
    )
    _setup_common(monkeypatch, runtime, catalog=catalog)

    response = await list_mcp_tools_runtime(
        MCPToolsListRequest(mcp_ids=["filesystem"], include_internal=True),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert len(response.results) == 1
    item = response.results[0]
    assert item.success is True
    assert item.listed_count == 2
    assert item.visible_count == 2
    assert {tool.name for tool in item.tools} == {"set_project_path", "list_directory"}


@pytest.mark.asyncio
async def test_list_mcp_tools_single_mcp_failure_does_not_block_others(monkeypatch):
    catalog = [
        {"id": "filesystem", "type": "mcp-server"},
        {"id": "code_index", "type": "mcp-server"},
    ]
    runtime = _FakeRuntime(
        {
            "filesystem": {
                "success": False,
                "tools": [],
                "error": "mcp_adapter_unavailable:filesystem",
                "metadata": {"mcp_runtime_domain": "sandbox"},
            },
            "code_index": {
                "success": True,
                "tools": [
                    {"name": "search_code_advanced", "description": "search", "inputSchema": {}},
                ],
                "metadata": {"mcp_runtime_domain": "backend"},
            },
        }
    )
    _setup_common(monkeypatch, runtime, catalog=catalog)

    response = await list_mcp_tools_runtime(
        MCPToolsListRequest(mcp_ids=["filesystem", "code_index"]),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert len(response.results) == 2
    by_id = {item.mcp_id: item for item in response.results}
    assert by_id["filesystem"].success is False
    assert by_id["filesystem"].error == "mcp_adapter_unavailable:filesystem"
    assert by_id["filesystem"].tools == []
    assert by_id["code_index"].success is True
    assert by_id["code_index"].visible_count == 1
