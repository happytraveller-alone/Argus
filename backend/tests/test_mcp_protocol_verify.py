import pytest

from app.services.agent.mcp.protocol_verify import (
    build_tool_args,
    run_protocol_verification,
)
from app.services.agent.mcp.runtime import MCPExecutionResult


def test_build_tool_args_generates_required_types():
    schema = {
        "type": "object",
        "required": ["name", "count", "flag", "items", "config"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "flag": {"type": "boolean"},
            "items": {"type": "array", "items": {"type": "string"}},
            "config": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
        },
    }

    args, error = build_tool_args(
        mcp_id="filesystem",
        tool_name="custom_unknown_tool",
        input_schema=schema,
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert error is None
    assert isinstance(args, dict)
    assert isinstance(args["name"], str)
    assert isinstance(args["count"], int)
    assert isinstance(args["flag"], bool)
    assert isinstance(args["items"], list)
    assert isinstance(args["config"], dict)
    assert isinstance(args["config"]["path"], str)


def test_build_tool_args_handles_enum_default_and_oneof():
    schema = {
        "type": "object",
        "required": ["mode", "value", "mixed"],
        "properties": {
            "mode": {"enum": ["strict", "loose"]},
            "value": {"default": 7},
            "mixed": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
        },
    }

    args, error = build_tool_args(
        mcp_id="filesystem",
        tool_name="another_tool",
        input_schema=schema,
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert error is None
    assert args["mode"] == "strict"
    assert args["value"] == 7
    assert isinstance(args["mixed"], int)


def test_build_tool_args_returns_error_when_schema_missing():
    args, error = build_tool_args(
        mcp_id="filesystem",
        tool_name="unknown_tool",
        input_schema=None,
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert args is None
    assert error == "arg_generation_failed:missing_input_schema"


def test_build_tool_args_known_code_index_find_files_includes_pattern():
    args, error = build_tool_args(
        mcp_id="code_index",
        tool_name="find_files",
        input_schema={"type": "object"},
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert error is None
    assert isinstance(args, dict)
    assert args.get("pattern")
    assert args.get("project_path") == "/tmp/project"
    assert args.get("project_root") == "/tmp/project"


def test_build_tool_args_known_qmd_get_uses_file_key():
    args, error = build_tool_args(
        mcp_id="qmd",
        tool_name="get",
        input_schema={"type": "object"},
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert error is None
    assert isinstance(args, dict)
    assert args.get("file") == "tmp/.probe.md"


def test_build_tool_args_filesystem_uses_absolute_probe_paths():
    args, error = build_tool_args(
        mcp_id="filesystem",
        tool_name="read_file",
        input_schema={"type": "object"},
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert error is None
    assert isinstance(args, dict)
    assert args.get("path") == "/tmp/project/tmp/.probe.txt"

    search_args, search_error = build_tool_args(
        mcp_id="filesystem",
        tool_name="search_files",
        input_schema={"type": "object"},
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )
    assert search_error is None
    assert isinstance(search_args, dict)
    assert search_args.get("path") == "/tmp/project/tmp"


class _RuntimeStub:
    def __init__(self):
        self.calls = []

    async def list_mcp_tools(self, mcp_name: str):
        return {
            "success": True,
            "tools": [
                {
                    "name": "custom_tool",
                    "description": "",
                    "inputSchema": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
                    },
                }
            ],
            "metadata": {"mcp_runtime_domain": "backend"},
        }

    async def call_mcp_tool(self, *, mcp_name, tool_name, arguments, agent_name=None, alias_used=None):
        self.calls.append((mcp_name, tool_name, dict(arguments or {})))
        return MCPExecutionResult(
            handled=True,
            success=True,
            data="ok",
            metadata={"mcp_runtime_domain": "backend"},
        )


@pytest.mark.asyncio
async def test_run_protocol_verification_success_for_generated_args():
    runtime = _RuntimeStub()
    result = await run_protocol_verification(
        runtime=runtime,
        mcp_id="filesystem",
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert result["success"] is True
    assert result["protocol_summary"]["discovered_count"] == 1
    assert result["protocol_summary"]["call_success_count"] == 1
    assert runtime.calls[0][1] == "custom_tool"


class _FilesystemRuntimeStub:
    required_mcps = ["filesystem", "code_index"]

    async def list_mcp_tools(self, mcp_name: str):
        return {
            "success": True,
            "tools": [
                {"name": "list_files", "description": "", "inputSchema": {"type": "object"}},
                {"name": "write_file", "description": "", "inputSchema": {"type": "object"}},
            ],
            "metadata": {"mcp_runtime_domain": "sandbox"},
        }

    async def call_mcp_tool(self, *, mcp_name, tool_name, arguments, agent_name=None, alias_used=None):
        assert tool_name == "list_files"
        return MCPExecutionResult(
            handled=True,
            success=True,
            data="ok",
            metadata={"mcp_runtime_domain": "sandbox"},
        )


@pytest.mark.asyncio
async def test_run_protocol_verification_skips_filesystem_write_tools_with_policy():
    runtime = _FilesystemRuntimeStub()
    result = await run_protocol_verification(
        runtime=runtime,
        mcp_id="filesystem",
        project_root="/tmp/project",
        filesystem_probe_file="tmp/.probe.txt",
        filesystem_media_probe_file="tmp/.probe.png",
        qmd_probe_file="tmp/.probe.md",
        code_probe_file="tmp/.probe.c",
        code_probe_function="mcp_probe_sum",
        code_probe_line=2,
    )

    assert result["success"] is True
    skip_checks = [item for item in result["checks"] if item["action"] == "policy/skip"]
    assert len(skip_checks) == 1
    assert skip_checks[0]["tool"] == "write_file"
    assert result["protocol_summary"]["skipped_unsupported_count"] == 1
    assert result["protocol_summary"]["required_gate"] == ["filesystem", "code_index"]
