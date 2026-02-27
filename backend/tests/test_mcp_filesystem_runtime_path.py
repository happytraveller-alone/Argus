from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime
from app.core.config import settings


def test_filesystem_runtime_uses_project_root_as_mount_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MCP_FILESYSTEM_SANDBOX_ARGS",
        "-y @modelcontextprotocol/server-filesystem .",
    )
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    filesystem_adapter = runtime.domain_adapters["filesystem"]["sandbox"]
    assert filesystem_adapter.args[-1] == str(tmp_path)
    assert "." not in filesystem_adapter.args


def test_filesystem_runtime_keeps_npx_package_token_when_no_mount_arg(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_FILESYSTEM_SANDBOX_ARGS", "-y @modelcontextprotocol/server-filesystem")
    monkeypatch.setattr(settings, "MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_QMD_ENABLED", False)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config={"otherConfig": {"mcpConfig": {"enabled": True}}},
        target_files=[],
    )

    filesystem_adapter = runtime.domain_adapters["filesystem"]["sandbox"]
    assert filesystem_adapter.args[-1] == str(tmp_path)
    if str(filesystem_adapter.command).endswith("npx"):
        assert "@modelcontextprotocol/server-filesystem" in filesystem_adapter.args
