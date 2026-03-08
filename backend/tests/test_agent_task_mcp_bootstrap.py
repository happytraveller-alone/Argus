from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.agent_tasks import _bootstrap_task_mcp_runtime
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
    def __init__(self, *, project_root: str, build_success: bool = True):
        self.project_root = project_root
        self.build_success = build_success
        self.calls = []

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
        if mcp_name == "code_index" and tool_name == "set_project_path":
            return MCPExecutionResult(
                handled=True,
                success=True,
                data="ok",
                metadata={"mcp_runtime_domain": "stdio"},
            )
        if mcp_name == "code_index" and tool_name == "build_deep_index":
            return MCPExecutionResult(
                handled=True,
                success=self.build_success,
                data="built" if self.build_success else "",
                error=None if self.build_success else "build_failed",
                metadata={"mcp_runtime_domain": "stdio"},
            )
        if mcp_name == "code_index" and tool_name == "refresh_index":
            return MCPExecutionResult(
                handled=True,
                success=True,
                data="refreshed",
                metadata={"mcp_runtime_domain": "stdio"},
            )
        return MCPExecutionResult(
            handled=False,
            success=False,
            error=f"unexpected:{mcp_name}:{tool_name}",
            metadata={"mcp_runtime_domain": "stdio"},
        )


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_binds_and_builds_deep_index(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(project_root=str(tmp_path), build_success=True)

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert result["filesystem"]["project_root_allowed"] is True
    assert result["code_index"]["index_tool"] == "build_deep_index"
    assert [call["tool_name"] for call in runtime.calls] == [
        "list_allowed_directories",
        "set_project_path",
        "build_deep_index",
    ]
    assert any("deep index" in message for message, _ in emitter.infos)


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_falls_back_to_refresh_index(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(project_root=str(tmp_path), build_success=False)

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert result["code_index"]["index_tool"] == "refresh_index"
    assert [call["tool_name"] for call in runtime.calls] == [
        "list_allowed_directories",
        "set_project_path",
        "build_deep_index",
        "refresh_index",
    ]
