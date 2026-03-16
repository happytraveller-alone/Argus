from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional

from app.core.config import settings


MCPCatalogType = Literal["mcp-server", "skill-pack"]


@dataclass(frozen=True)
class McpDomainStatus:
    enabled: bool
    startup_ready: bool
    startup_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class McpCatalogItem:
    id: str
    name: str
    type: MCPCatalogType
    enabled: bool
    description: str
    executionFunctions: List[str]
    inputInterface: List[str]
    outputInterface: List[str]
    includedSkills: List[str]
    verificationTools: List[str]
    source: str
    runtime_mode: str = "stdio_only"
    backend: Optional[McpDomainStatus] = None
    sandbox: Optional[McpDomainStatus] = None
    required: bool = True
    startup_ready: bool = True
    startup_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        output = asdict(self)
        if self.backend is not None:
            output["backend"] = self.backend.to_dict()
        else:
            output["backend"] = None
        if self.sandbox is not None:
            output["sandbox"] = self.sandbox.to_dict()
        else:
            output["sandbox"] = None
        return output


_CORE_MCP_DEFINITIONS: Dict[str, Dict[str, Any]] = {}

def _command_ready(command: str) -> tuple[bool, Optional[str]]:
    executable = str(command or "").strip()
    if not executable:
        return False, "missing_command"
    if os.path.isabs(executable):
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return True, None
        return False, "command_not_found"
    if shutil.which(executable):
        return True, None
    return False, "command_not_found"


def _runtime_entry(runtime_policy: Optional[Dict[str, Any]], mcp_id: str) -> Dict[str, Any]:
    if isinstance(runtime_policy, dict):
        candidate = runtime_policy.get(mcp_id)
        if isinstance(candidate, dict):
            return candidate
    return {}


def build_mcp_catalog(
    *,
    mcp_enabled: Optional[bool] = None,
    runtime_policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    runtime_enabled = bool(getattr(settings, "MCP_ENABLED", True) if mcp_enabled is None else mcp_enabled)
    catalog: List[Dict[str, Any]] = []

    for mcp_id, definition in _CORE_MCP_DEFINITIONS.items():
        policy = _runtime_entry(runtime_policy, mcp_id)
        enabled = bool(policy.get("enabled", getattr(settings, definition["enabled_setting"], True)))
        command = str(getattr(settings, definition["command_setting"], "") or "").strip()
        ready, reason = _command_ready(command)
        startup_ready = bool(runtime_enabled and enabled and ready)
        startup_error = None if startup_ready else (reason or ("disabled" if not enabled else "mcp_disabled"))
        item = McpCatalogItem(
            id=mcp_id,
            name=definition["name"],
            type="mcp-server",
            enabled=bool(runtime_enabled and enabled),
            description=definition["description"],
            executionFunctions=list(definition["executionFunctions"]),
            inputInterface=list(definition["inputInterface"]),
            outputInterface=list(definition["outputInterface"]),
            includedSkills=list(definition["includedSkills"]),
            verificationTools=list(definition["verificationTools"]),
            source=definition["source"],
            runtime_mode="stdio_only",
            backend=None,
            sandbox=None,
            required=True,
            startup_ready=startup_ready,
            startup_error=startup_error,
        )
        catalog.append(item.to_dict())

    return catalog
