from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
import uuid


ProbeAction = Literal["tool", "cleanup_file"]


@dataclass(frozen=True)
class MCPProbeCheck:
    step: str
    action: ProbeAction = "tool"
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    expect_success: bool = True
    accept_any_result: bool = False
    required: bool = True
    cleanup_path: Optional[str] = None


MCP_VERIFICATION_TOOLS: Dict[str, List[str]] = {
    "filesystem": ["read_file"],
    "code_index": ["extract_function", "list_files", "locate_enclosing_function"],
    "sequentialthinking": ["sequential_thinking", "reasoning_trace"],
    "qmd": ["qmd_status", "qmd_query", "qmd_get", "qmd_multi_get"],
}


def get_verification_tools(mcp_id: str) -> List[str]:
    return list(MCP_VERIFICATION_TOOLS.get(str(mcp_id or "").strip(), []))


def build_probe_checks(
    *,
    mcp_id: str,
    filesystem_probe_file: Optional[str] = None,
    code_probe_file: Optional[str] = None,
    code_probe_function: Optional[str] = None,
    code_probe_line: Optional[int] = None,
) -> List[MCPProbeCheck]:
    normalized_id = str(mcp_id or "").strip().lower()
    if normalized_id == "filesystem":
        probe_rel_path = str(filesystem_probe_file or "").strip()
        if not probe_rel_path:
            probe_rel_path = f"tmp/.mcp_probe_{uuid.uuid4().hex}.txt"
        probe_keyword = "mcp verify filesystem probe"
        return [
            MCPProbeCheck(
                step="read_probe_file",
                tool_name="read_file",
                arguments={"file_path": probe_rel_path},
            ),
        ]
    if normalized_id == "code_index":
        probe_file = str(code_probe_file or "").strip() or "tmp/.mcp_verify_code_probe.c"
        probe_function = str(code_probe_function or "").strip() or "mcp_probe_sum"
        probe_line = int(code_probe_line or 3)
        return [
            MCPProbeCheck(
                step="list_files_probe",
                tool_name="list_files",
                arguments={
                    "directory": "tmp",
                    "pattern": "*.c",
                },
            ),
            MCPProbeCheck(
                step="extract_function_probe",
                tool_name="extract_function",
                arguments={
                    "code": (
                        f"int {probe_function}(int a, int b) {{\n"
                        "    return a + b;\n"
                        "}\n"
                    ),
                    "file_name": probe_file.split("/")[-1],
                    "file_path": probe_file,
                    "line": probe_line,
                },
            ),
            MCPProbeCheck(
                step="locate_enclosing_function_probe",
                tool_name="locate_enclosing_function",
                arguments={
                    "file_path": probe_file,
                    "line_start": probe_line,
                },
            )
        ]
    if normalized_id == "sequentialthinking":
        return [
            MCPProbeCheck(
                step="sequential_thinking_probe",
                tool_name="sequential_thinking",
                arguments={
                    "goal": "mcp_verify_sequential",
                    "thought": "mcp_verify_sequential",
                    "nextThoughtNeeded": False,
                    "thoughtNumber": 1,
                    "totalThoughts": 1,
                },
            ),
            MCPProbeCheck(
                step="reasoning_trace_probe",
                tool_name="reasoning_trace",
                arguments={
                    "goal": "mcp_verify_reasoning",
                    "thought": "mcp_verify_reasoning",
                    "nextThoughtNeeded": False,
                    "thoughtNumber": 1,
                    "totalThoughts": 1,
                },
            )
        ]
    if normalized_id == "qmd":
        return [
            MCPProbeCheck(step="qmd_status_probe", tool_name="qmd_status", arguments={}),
            MCPProbeCheck(
                step="qmd_query_probe",
                tool_name="qmd_query",
                arguments={"query": "mcp_probe_sum"},
            ),
            MCPProbeCheck(
                step="qmd_get_probe",
                tool_name="qmd_get",
                arguments={"doc_id": "__mcp_probe_missing_doc__"},
                accept_any_result=True,
            ),
            MCPProbeCheck(
                step="qmd_multi_get_probe",
                tool_name="qmd_multi_get",
                arguments={"doc_ids": ["__mcp_probe_missing_doc__"]},
                accept_any_result=True,
            ),
        ]
    return []
