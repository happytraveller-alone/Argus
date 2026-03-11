from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.agent_tasks import _bootstrap_task_mcp_runtime, _build_task_mcp_runtime
from app.services.agent.mcp.runtime import MCPExecutionResult


class _Emitter:
    def __init__(self):
        self.infos = []
        self.errors = []

    async def emit_info(self, message: str, metadata=None):
        self.infos.append((message, metadata or {}))

    async def emit_error(self, message: str, metadata=None):
        self.errors.append((message, metadata or {}))


class _Runtime:
    def __init__(
        self,
        *,
        project_root: str,
        build_success: bool = True,
        codebadger_success: bool = True,
        codebadger_registered: bool = False,
    ):
        self.project_root = project_root
        self.build_success = build_success
        self.codebadger_success = codebadger_success
        self.calls = []
        self.domain_adapters = {"codebadger": {"backend": object()}} if codebadger_registered else {}

    async def call_mcp_tool(self, *, mcp_name: str, tool_name: str, arguments, agent_name=None, alias_used=None):
        self.calls.append(
            {
                "mcp_name": mcp_name,
                "tool_name": tool_name,
                "arguments": dict(arguments or {}),
                "agent_name": agent_name,
                "alias_used": alias_used,
            }
        )
        if mcp_name == "filesystem" and tool_name == "list_allowed_directories":
            return MCPExecutionResult(
                handled=True,
                success=True,
                data=f"Allowed directories:\\n{self.project_root}",
                metadata={"mcp_runtime_domain": "stdio"},
            )
        if mcp_name == "codebadger" and tool_name == "health_status":
            return MCPExecutionResult(
                handled=self.codebadger_success,
                success=self.codebadger_success,
                data={"status": "healthy" if self.codebadger_success else "unhealthy"},
                error=None if self.codebadger_success else "codebadger_unhealthy",
                metadata={"mcp_runtime_domain": "backend"},
            )
        return MCPExecutionResult(
            handled=False,
            success=False,
            error=f"unexpected:{mcp_name}:{tool_name}",
            metadata={"mcp_runtime_domain": "stdio"},
        )


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_only_binds_filesystem_root(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(project_root=str(tmp_path), build_success=True)

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert result["filesystem"]["project_root_allowed"] is True
    assert [call["tool_name"] for call in runtime.calls] == [
        "list_allowed_directories",
    ]
    assert not any("code_index" in message for message, _ in emitter.infos)
    assert not any("CodeBadger" in message for message, _ in emitter.infos)


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_does_not_touch_code_index_on_bootstrap(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(project_root=str(tmp_path), build_success=False)

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )
    assert result["filesystem"]["project_root_allowed"] is True
    assert [call["tool_name"] for call in runtime.calls] == [
        "list_allowed_directories",
    ]


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_checks_codebadger_when_registered(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(
        project_root=str(tmp_path),
        build_success=True,
        codebadger_registered=True,
    )

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert result["codebadger"]["status"] == "healthy"
    assert [call["tool_name"] for call in runtime.calls] == [
        "list_allowed_directories",
        "health_status",
    ]
    assert any("CodeBadger" in message for message, _ in emitter.infos)


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_blocks_when_codebadger_health_check_fails(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(
        project_root=str(tmp_path),
        build_success=True,
        codebadger_success=False,
        codebadger_registered=True,
    )

    with pytest.raises(RuntimeError, match="CodeBadger MCP 健康检查失败"):
        await _bootstrap_task_mcp_runtime(
            runtime,
            project_root=str(tmp_path),
            event_emitter=emitter,
        )


def test_build_task_mcp_runtime_skips_codebadger_when_endpoint_unreachable(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODEBADGER_ENABLED", True)
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODEBADGER_BACKEND_URL",
        "http://codebadger-mcp:4242/mcp",
    )
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODEBADGER_RUNTIME_MODE",
        "backend_only",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.probe_mcp_endpoint_readiness",
        lambda *args, **kwargs: (False, "healthcheck_failed"),
    )

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=None,
    )

    assert "codebadger" not in runtime.domain_adapters
    assert "codebadger" not in runtime.runtime_modes
    assert runtime.required_mcps == ["filesystem"]


def test_build_task_mcp_runtime_registers_codebadger_when_endpoint_reachable(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODEBADGER_ENABLED", True)
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODEBADGER_BACKEND_URL",
        "http://codebadger-mcp:4242/mcp",
    )
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODEBADGER_RUNTIME_MODE",
        "backend_only",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.probe_mcp_endpoint_readiness",
        lambda *args, **kwargs: (True, None),
    )

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=None,
    )

    assert "codebadger" in runtime.domain_adapters
    assert "backend" in runtime.domain_adapters["codebadger"]
    assert runtime.runtime_modes["codebadger"] == "backend_only"
