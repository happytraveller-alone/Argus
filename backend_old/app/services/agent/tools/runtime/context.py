from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolFailureState:
    error: str = ""
    error_code: str = "internal_error"
    diagnostics: list[str] = field(default_factory=list)
    reflection: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallContext:
    tool_name: str
    requested_tool_name: str
    phase: str = ""
    agent_type: str = ""
    raw_input: Dict[str, Any] = field(default_factory=dict)
    normalized_input: Dict[str, Any] = field(default_factory=dict)
    validated_input: Dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    caller: str = ""
    trace_id: str = ""
    runtime_policy: Dict[str, Any] = field(default_factory=dict)
    failure_state: Optional[ToolFailureState] = None
