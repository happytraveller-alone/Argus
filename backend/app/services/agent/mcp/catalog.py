from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional

from app.core.config import settings
from .health_probe import probe_mcp_endpoint_readiness


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


_CORE_MCP_DEFINITIONS = {
    "filesystem": {
        "name": "Filesystem MCP",
        "description": "任务解压目录挂载（只读），支持项目文件读取与目录访问。",
        "executionFunctions": ["read_file", "list_directory", "search_files", "get_file_info"],
        "inputInterface": ["path/file_path", "directory", "pattern"],
        "outputInterface": ["content", "metadata.file_path", "entries"],
        "includedSkills": ["read_file"],
        "verificationTools": ["read_file"],
        "source": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        "command_setting": "MCP_FILESYSTEM_COMMAND",
        "enabled_setting": "MCP_FILESYSTEM_ENABLED",
    },
}


_CODEBADGER_MCP_DEFINITION = {
    "name": "CodeBadger MCP",
    "description": "通过外部 CodeBadger HTTP MCP 服务提供源码级 CPG / CFG / DFG 能力。",
    "executionFunctions": ["generate_cpg", "run_cpgql_query", "get_cfg"],
    "inputInterface": ["source_path", "language", "query"],
    "outputInterface": ["response", "codebase_hash", "status"],
    "includedSkills": ["joern_reachability_verify"],
    "verificationTools": ["health_status"],
    "source": "https://github.com/Lekssays/codebadger",
    "enabled_setting": "MCP_CODEBADGER_ENABLED",
    "backend_url_setting": "MCP_CODEBADGER_BACKEND_URL",
}


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

    codebadger_enabled = bool(getattr(settings, _CODEBADGER_MCP_DEFINITION["enabled_setting"], False))
    if codebadger_enabled:
        policy = _runtime_entry(runtime_policy, "codebadger")
        enabled = bool(policy.get("enabled", codebadger_enabled))
        backend_url = str(
            getattr(settings, _CODEBADGER_MCP_DEFINITION["backend_url_setting"], "") or ""
        ).strip()
        backend_ready = False
        backend_error: Optional[str] = None
        if runtime_enabled and enabled and backend_url:
            backend_ready, backend_error = probe_mcp_endpoint_readiness(
                backend_url,
                timeout=1.5,
            )
        elif enabled:
            backend_error = "missing_backend_url"
        else:
            backend_error = "disabled"
        item = McpCatalogItem(
            id="codebadger",
            name=_CODEBADGER_MCP_DEFINITION["name"],
            type="mcp-server",
            enabled=bool(runtime_enabled and enabled),
            description=_CODEBADGER_MCP_DEFINITION["description"],
            executionFunctions=list(_CODEBADGER_MCP_DEFINITION["executionFunctions"]),
            inputInterface=list(_CODEBADGER_MCP_DEFINITION["inputInterface"]),
            outputInterface=list(_CODEBADGER_MCP_DEFINITION["outputInterface"]),
            includedSkills=list(_CODEBADGER_MCP_DEFINITION["includedSkills"]),
            verificationTools=list(_CODEBADGER_MCP_DEFINITION["verificationTools"]),
            source=_CODEBADGER_MCP_DEFINITION["source"],
            runtime_mode="backend_only",
            backend=McpDomainStatus(
                enabled=bool(runtime_enabled and enabled),
                startup_ready=backend_ready,
                startup_error=backend_error,
            ),
            sandbox=None,
            required=False,
            startup_ready=backend_ready,
            startup_error=backend_error,
        )
        catalog.append(item.to_dict())

    return catalog
