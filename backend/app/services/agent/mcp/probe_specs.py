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


MCP_VERIFICATION_TOOLS: Dict[str, List[str]] = {}


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
    _ = mcp_id
    _ = filesystem_probe_file
    _ = code_probe_file
    _ = code_probe_function
    _ = code_probe_line
    return []
