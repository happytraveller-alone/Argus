from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


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
