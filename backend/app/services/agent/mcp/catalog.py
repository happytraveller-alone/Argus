from __future__ import annotations

import os
import socket
import shutil
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import settings
from .daemon_manager import (
    resolve_code_index_backend_url,
    resolve_filesystem_backend_url,
    resolve_sequential_backend_url,
)
from .probe_specs import get_verification_tools


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
    runtime_mode: str = "backend_then_sandbox"
    backend: Optional[McpDomainStatus] = None
    sandbox: Optional[McpDomainStatus] = None
    required: bool = True
    startup_ready: bool = True
    startup_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        output = asdict(self)
        if self.backend is not None:
            output["backend"] = self.backend.to_dict()
        if self.sandbox is not None:
            output["sandbox"] = self.sandbox.to_dict()
        return output


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


def _http_endpoint_ready(url: Optional[str]) -> tuple[bool, Optional[str]]:
    ready, reason = _validate_http_endpoint(url)
    if not ready:
        return False, reason

    endpoint = str(url or "").strip()
    parsed = urlparse(endpoint)
    health_url = urlunparse(parsed._replace(path="/health", params="", query="", fragment=""))
    fallback_to_tcp_probe = False
    try:
        with httpx.Client(timeout=1.5, follow_redirects=True) as client:
            response = client.get(health_url)
        if response.status_code == 200:
            return True, None
        if int(response.status_code) in {404, 405, 501}:
            fallback_to_tcp_probe = True
        else:
            return False, f"healthcheck_failed:status_{int(response.status_code)}@{health_url}"
    except Exception as exc:
        if isinstance(exc, httpx.RemoteProtocolError):
            fallback_to_tcp_probe = True
        else:
            return False, f"healthcheck_failed:{exc.__class__.__name__}@{health_url}"
    if fallback_to_tcp_probe:
        host = str(parsed.hostname or "").strip()
        if not host:
            return False, f"healthcheck_failed:tcp_unreachable:missing_host@{health_url}"
        port = int(parsed.port) if parsed.port else (443 if str(parsed.scheme).lower() == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True, None
        except Exception as exc:
            return False, f"healthcheck_failed:tcp_unreachable:{exc.__class__.__name__}@{health_url}"
    return True, None


def _validate_http_endpoint(url: Optional[str]) -> tuple[bool, Optional[str]]:
    endpoint = str(url or "").strip()
    if not endpoint:
        return False, "missing_endpoint"
    if endpoint.startswith(("http://", "https://")):
        return True, None
    return False, "invalid_endpoint"


def _runtime_entry(
    runtime_policy: Optional[Dict[str, Any]],
    mcp_id: str,
) -> Dict[str, Any]:
    if isinstance(runtime_policy, dict):
        candidate = runtime_policy.get(mcp_id)
        if isinstance(candidate, dict):
            return candidate
    return {}


def _default_runtime_mode(
    runtime_policy: Optional[Dict[str, Any]],
    fallback: str = "backend_then_sandbox",
) -> str:
    if isinstance(runtime_policy, dict):
        mode = runtime_policy.get("default_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return fallback


def _build_domain_status(
    *,
    enabled: bool,
    checker: tuple[bool, Optional[str]],
) -> McpDomainStatus:
    ready, reason = checker
    if not enabled:
        return McpDomainStatus(enabled=False, startup_ready=False, startup_error="disabled")
    return McpDomainStatus(enabled=True, startup_ready=bool(ready), startup_error=reason)


def _build_domain_status_with_stdio_fallback(
    *,
    enabled: bool,
    http_checker: tuple[bool, Optional[str]],
    stdio_command: str,
) -> McpDomainStatus:
    if not enabled:
        return McpDomainStatus(enabled=False, startup_ready=False, startup_error="disabled")
    http_ready, http_reason = http_checker
    if http_ready:
        return McpDomainStatus(enabled=True, startup_ready=True, startup_error=None)

    stdio_ready, stdio_reason = _command_ready(stdio_command)
    if stdio_ready:
        fallback_reason = "http_unreachable_stdio_fallback"
        if http_reason:
            fallback_reason = f"{fallback_reason}:{http_reason}"
        return McpDomainStatus(
            enabled=True,
            startup_ready=True,
            startup_error=fallback_reason,
        )

    combined_reason = "; ".join(
        str(item).strip()
        for item in (http_reason, stdio_reason)
        if str(item).strip()
    )
    return McpDomainStatus(
        enabled=True,
        startup_ready=False,
        startup_error=combined_reason or "startup_check_failed",
    )


def _combine_startup_status(domains: List[McpDomainStatus], enabled: bool) -> tuple[bool, Optional[str]]:
    if not enabled:
        return False, "disabled"
    active_domains = [domain for domain in domains if domain.enabled]
    if not active_domains:
        return False, "disabled"
    errors = [domain.startup_error for domain in active_domains if not domain.startup_ready]
    if errors:
        return False, "; ".join(str(item) for item in errors if item)
    return True, None


def build_mcp_catalog(
    *,
    mcp_enabled: Optional[bool] = None,
    runtime_policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    runtime_enabled = (
        bool(getattr(settings, "MCP_ENABLED", True))
        if mcp_enabled is None
        else bool(mcp_enabled)
    )
    source_override = str(getattr(settings, "MCP_CATALOG_SOURCE_URL", "") or "").strip()

    default_mode = _default_runtime_mode(
        runtime_policy,
        str(getattr(settings, "MCP_RUNTIME_MODE_DEFAULT", "backend_then_sandbox")),
    )

    def _runtime_mode_for(mcp_id: str, setting_name: str) -> str:
        entry = _runtime_entry(runtime_policy, mcp_id)
        mode = entry.get("runtime_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
        return str(getattr(settings, setting_name, default_mode) or default_mode)

    def _domain_enabled_for(mcp_id: str, domain: str, setting_name: str) -> bool:
        entry = _runtime_entry(runtime_policy, mcp_id)
        policy_key = f"{domain}_enabled"
        if isinstance(entry.get(policy_key), bool):
            return bool(entry[policy_key])
        return bool(getattr(settings, setting_name, False))

    filesystem_backend_url = resolve_filesystem_backend_url(settings)
    filesystem_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("filesystem", "backend", "MCP_FILESYSTEM_ENABLED"),
        checker=_http_endpoint_ready(filesystem_backend_url)
        if filesystem_backend_url
        else _command_ready(str(getattr(settings, "MCP_FILESYSTEM_COMMAND", "npx"))),
    )
    filesystem_sandbox_url = str(getattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "") or "").strip()
    if not filesystem_sandbox_url:
        filesystem_sandbox_url = filesystem_backend_url
    filesystem_sandbox = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for("filesystem", "sandbox", "MCP_FILESYSTEM_SANDBOX_ENABLED"),
        checker=_http_endpoint_ready(filesystem_sandbox_url)
        if filesystem_sandbox_url
        else _command_ready(str(getattr(settings, "MCP_FILESYSTEM_SANDBOX_COMMAND", "npx"))),
    )
    filesystem_enabled = bool(filesystem_backend.enabled or filesystem_sandbox.enabled)
    filesystem_startup_ready, filesystem_startup_error = _combine_startup_status(
        [filesystem_backend, filesystem_sandbox],
        filesystem_enabled,
    )

    code_index_backend_url = resolve_code_index_backend_url(settings)
    code_index_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("code_index", "backend", "MCP_CODE_INDEX_ENABLED"),
        checker=_http_endpoint_ready(code_index_backend_url)
        if code_index_backend_url
        else _command_ready(str(getattr(settings, "MCP_CODE_INDEX_COMMAND", "code-index-mcp"))),
    )
    code_index_sandbox_url = str(getattr(settings, "MCP_CODE_INDEX_SANDBOX_URL", "") or "").strip()
    if not code_index_sandbox_url:
        code_index_sandbox_url = code_index_backend_url
    code_index_sandbox = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for("code_index", "sandbox", "MCP_CODE_INDEX_SANDBOX_ENABLED"),
        checker=_http_endpoint_ready(code_index_sandbox_url)
        if code_index_sandbox_url
        else _command_ready(str(getattr(settings, "MCP_CODE_INDEX_SANDBOX_COMMAND", "code-index-mcp"))),
    )
    code_index_enabled = bool(code_index_backend.enabled or code_index_sandbox.enabled)
    code_index_startup_ready, code_index_startup_error = _combine_startup_status(
        [code_index_backend, code_index_sandbox],
        code_index_enabled,
    )

    seq_backend_url = resolve_sequential_backend_url(settings)
    seq_backend = _build_domain_status_with_stdio_fallback(
        enabled=runtime_enabled
        and _domain_enabled_for(
            "sequentialthinking",
            "backend",
            "MCP_SEQUENTIAL_THINKING_ENABLED",
        ),
        http_checker=_http_endpoint_ready(seq_backend_url),
        stdio_command=str(getattr(settings, "MCP_SEQUENTIAL_THINKING_COMMAND", "npx")),
    )
    seq_sandbox_url = str(getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "") or "").strip()
    if not seq_sandbox_url:
        seq_sandbox_url = seq_backend_url
    seq_sandbox = _build_domain_status_with_stdio_fallback(
        enabled=runtime_enabled
        and _domain_enabled_for(
            "sequentialthinking",
            "sandbox",
            "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED",
        ),
        http_checker=_http_endpoint_ready(seq_sandbox_url),
        stdio_command=str(getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND", "npx")),
    )
    seq_enabled = bool(seq_backend.enabled or seq_sandbox.enabled)
    seq_startup_ready, seq_startup_error = _combine_startup_status(
        [seq_backend, seq_sandbox],
        seq_enabled,
    )

    items = [
        McpCatalogItem(
            id="filesystem",
            name="Filesystem MCP",
            type="mcp-server",
            enabled=filesystem_enabled,
            description="任务解压目录挂载（只读），支持项目文件读取与目录查看。",
            executionFunctions=["read_file", "list_directory", "search_files", "get_file_info"],
            inputInterface=["path/file_path", "directory", "pattern"],
            outputInterface=["content", "metadata.file_path", "entries"],
            includedSkills=["read_file", "search_code"],
            verificationTools=get_verification_tools("filesystem"),
            source="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
            runtime_mode=_runtime_mode_for("filesystem", "MCP_FILESYSTEM_RUNTIME_MODE"),
            backend=filesystem_backend,
            sandbox=filesystem_sandbox,
            required=True,
            startup_ready=filesystem_startup_ready,
            startup_error=filesystem_startup_error,
        ),
        McpCatalogItem(
            id="code_index",
            name="Code Index MCP",
            type="mcp-server",
            enabled=code_index_enabled,
            description="代码检索、符号提取、文件摘要与函数定位能力。",
            executionFunctions=["find_files", "search_code_advanced", "get_symbol_body", "get_file_summary"],
            inputInterface=["query/keyword", "path/file_path", "glob/file_pattern", "line_start"],
            outputInterface=["matches", "symbols", "file_summary", "metadata.engine"],
            includedSkills=[
                "extract_function",
                "list_files",
                "locate_enclosing_function",
            ],
            verificationTools=get_verification_tools("code_index"),
            source="https://github.com/johnhuang316/code-index-mcp",
            runtime_mode=_runtime_mode_for("code_index", "MCP_CODE_INDEX_RUNTIME_MODE"),
            backend=code_index_backend,
            sandbox=code_index_sandbox,
            required=True,
            startup_ready=code_index_startup_ready,
            startup_error=code_index_startup_error,
        ),
        McpCatalogItem(
            id="sequentialthinking",
            name="Sequential Thinking MCP",
            type="mcp-server",
            enabled=seq_enabled,
            description="序列化推理与分步思考能力。",
            executionFunctions=["sequential_thinking", "reasoning_trace"],
            inputInterface=["goal", "constraints", "step_index"],
            outputInterface=["reasoning_steps", "next_action", "stop_signal"],
            includedSkills=["sequential_thinking", "reasoning_trace", "brainstorming", "step_reasoning"],
            verificationTools=get_verification_tools("sequentialthinking"),
            source="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
            runtime_mode=_runtime_mode_for(
                "sequentialthinking",
                "MCP_SEQUENTIAL_THINKING_RUNTIME_MODE",
            ),
            backend=seq_backend,
            sandbox=seq_sandbox,
            required=False,
            startup_ready=seq_startup_ready,
            startup_error=seq_startup_error,
        ),
    ]

    catalog = [item.to_dict() for item in items]
    if source_override:
        for item in catalog:
            item["catalog_source"] = source_override
    return catalog
