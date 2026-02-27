from types import SimpleNamespace
import zipfile

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import MCPVerifyRequest, verify_mcp_runtime
from app.services.agent.mcp.runtime import MCPExecutionResult


class _FakeExecuteResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    async def execute(self, *args, **kwargs):
        return _FakeExecuteResult()


class _RuntimeSuccess:
    required_mcps = ["filesystem"]

    def __init__(self):
        self.list_calls = []
        self.tool_calls = []

    async def list_mcp_tools(self, mcp_name: str):
        self.list_calls.append(str(mcp_name))
        return {
            "success": True,
            "tools": [
                {
                    "name": "list_directory",
                    "description": "list",
                    "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
                {
                    "name": "read_file",
                    "description": "read",
                    "inputSchema": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
                    },
                },
            ],
            "metadata": {"mcp_runtime_domain": "sandbox"},
        }

    async def call_mcp_tool(self, *, mcp_name, tool_name, arguments, agent_name=None, alias_used=None):
        self.tool_calls.append((mcp_name, tool_name, dict(arguments or {})))
        return MCPExecutionResult(
            handled=True,
            success=True,
            data="ok",
            metadata={"mcp_runtime_domain": "sandbox"},
        )


class _RuntimeArgFailure(_RuntimeSuccess):
    async def list_mcp_tools(self, mcp_name: str):
        self.list_calls.append(str(mcp_name))
        return {
            "success": True,
            "tools": [
                {
                    "name": "custom_tool",
                    "description": "unknown",
                    "inputSchema": {},
                }
            ],
            "metadata": {"mcp_runtime_domain": "sandbox"},
        }

    async def call_mcp_tool(self, *, mcp_name, tool_name, arguments, agent_name=None, alias_used=None):
        raise AssertionError("call_mcp_tool should not be called when argument generation fails")


class _RuntimeCallFailure(_RuntimeSuccess):
    async def call_mcp_tool(self, *, mcp_name, tool_name, arguments, agent_name=None, alias_used=None):
        self.tool_calls.append((mcp_name, tool_name, dict(arguments or {})))
        return MCPExecutionResult(
            handled=True,
            success=False,
            error="tool_failed",
            metadata={"mcp_runtime_domain": "backend"},
        )


def _prepare_archive(tmp_path):
    archive_path = tmp_path / "libplist.zip"
    with zipfile.ZipFile(archive_path, "w") as zip_ref:
        zip_ref.writestr("libplist/src/main.c", "int main() { return 0; }\n")
    return archive_path


@pytest.mark.asyncio
async def test_verify_mcp_runtime_filesystem_protocol_success(tmp_path, monkeypatch):
    archive_path = _prepare_archive(tmp_path)
    fake_project = SimpleNamespace(id="project-1", name="libplist", source_type="zip")

    async def _fake_resolve_verify_project(*, db, current_user):
        return fake_project, str(archive_path), True

    runtime = _RuntimeSuccess()
    captured: dict[str, object] = {}

    def _fake_build_task_mcp_runtime(*, project_root, user_config, target_files, project_id=None, **kwargs):
        captured["project_root"] = project_root
        captured["target_files"] = list(target_files or [])
        captured["active_mcp_ids"] = list(kwargs.get("active_mcp_ids") or [])
        return runtime

    monkeypatch.setattr(config_module, "_resolve_verify_project", _fake_resolve_verify_project)
    monkeypatch.setattr(agent_tasks_module, "_build_task_mcp_runtime", _fake_build_task_mcp_runtime)

    response = await verify_mcp_runtime(
        MCPVerifyRequest(mcp_id="filesystem"),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.success is True
    assert response.mcp_id == "filesystem"
    assert response.project_context.get("fallback_used") is True
    assert captured["project_root"].endswith("/libplist")
    assert captured["active_mcp_ids"] == ["filesystem"]
    assert len(captured["target_files"]) == 2
    assert all(str(path).startswith("tmp/.mcp_verify_filesystem_probe_") for path in captured["target_files"])
    assert runtime.list_calls == ["filesystem"]
    assert len(runtime.tool_calls) == 2
    assert response.verification_tools == ["list_directory", "read_file"]
    assert response.discovered_tools[0]["name"] == "list_directory"
    assert response.protocol_summary["list_tools_success"] is True
    assert response.protocol_summary["discovered_count"] == 2
    assert response.protocol_summary["call_success_count"] == 2
    assert response.protocol_summary["call_failed_count"] == 0
    assert response.protocol_summary["skipped_unsupported_count"] == 0
    assert response.protocol_summary["required_gate"] == ["filesystem"]


@pytest.mark.asyncio
async def test_verify_mcp_runtime_marks_arg_generation_failure(tmp_path, monkeypatch):
    archive_path = _prepare_archive(tmp_path)
    fake_project = SimpleNamespace(id="project-1", name="libplist", source_type="zip")

    async def _fake_resolve_verify_project(*, db, current_user):
        return fake_project, str(archive_path), False

    runtime = _RuntimeArgFailure()

    monkeypatch.setattr(config_module, "_resolve_verify_project", _fake_resolve_verify_project)
    monkeypatch.setattr(
        agent_tasks_module,
        "_build_task_mcp_runtime",
        lambda **kwargs: runtime,
    )

    response = await verify_mcp_runtime(
        MCPVerifyRequest(mcp_id="filesystem"),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.success is False
    assert response.protocol_summary["arg_failed_count"] == 1
    assert response.protocol_summary["call_failed_count"] == 1
    failing = [item for item in response.checks if item.step == "tools_call::custom_tool"][0]
    assert failing.success is False
    assert str(failing.error).startswith("arg_generation_failed:")


@pytest.mark.asyncio
async def test_verify_mcp_runtime_marks_tool_call_failure(tmp_path, monkeypatch):
    archive_path = _prepare_archive(tmp_path)
    fake_project = SimpleNamespace(id="project-1", name="libplist", source_type="zip")

    async def _fake_resolve_verify_project(*, db, current_user):
        return fake_project, str(archive_path), False

    runtime = _RuntimeCallFailure()

    monkeypatch.setattr(config_module, "_resolve_verify_project", _fake_resolve_verify_project)
    monkeypatch.setattr(
        agent_tasks_module,
        "_build_task_mcp_runtime",
        lambda **kwargs: runtime,
    )

    response = await verify_mcp_runtime(
        MCPVerifyRequest(mcp_id="filesystem"),
        db=_FakeDB(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.success is False
    assert response.protocol_summary["call_failed_count"] == 2
    assert any(not item.success and item.action == "tools/call" for item in response.checks)


@pytest.mark.asyncio
async def test_verify_mcp_runtime_rejects_unknown_mcp():
    with pytest.raises(HTTPException):
        await verify_mcp_runtime(
            MCPVerifyRequest(mcp_id="unknown_mcp"),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )


@pytest.mark.asyncio
async def test_verify_mcp_runtime_rejects_qmd():
    with pytest.raises(HTTPException):
        await verify_mcp_runtime(
            MCPVerifyRequest(mcp_id="qmd"),
            db=_FakeDB(),
            current_user=SimpleNamespace(id="user-1"),
        )
