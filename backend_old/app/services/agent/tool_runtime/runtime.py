from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx
from fastmcp import Client as MCPClient
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from urllib.parse import urlparse, urlunparse

from app.core.config import settings

from .health_probe import probe_endpoint_readiness
from .router import ToolRoute, ToolRouter
from .write_scope import TaskWriteScopeGuard, WriteScopeDecision

logger = logging.getLogger(__name__)


def _normalize_tool_descriptor(tool: Any) -> Optional[Dict[str, Any]]:
    candidate: Dict[str, Any]
    if isinstance(tool, dict):
        candidate = dict(tool)
    elif hasattr(tool, "model_dump"):
        try:
            dumped = tool.model_dump()  # type: ignore[attr-defined]
        except Exception:
            dumped = None
        if not isinstance(dumped, dict):
            return None
        candidate = dict(dumped)
    else:
        candidate = {}
        for field in (
            "name",
            "description",
            "inputSchema",
            "input_schema",
            "schema",
            "parameters",
        ):
            if hasattr(tool, field):
                candidate[field] = getattr(tool, field)

    name = str(
        candidate.get("name")
        or candidate.get("tool")
        or candidate.get("id")
        or ""
    ).strip()
    if not name:
        return None

    description = str(candidate.get("description") or "").strip()
    input_schema = (
        candidate.get("inputSchema")
        or candidate.get("input_schema")
        or candidate.get("schema")
        or candidate.get("parameters")
    )
    if not isinstance(input_schema, dict):
        input_schema = {}
    return {
        "name": name,
        "description": description,
        "inputSchema": dict(input_schema),
    }


def _normalize_tools_payload(payload: Any) -> List[Dict[str, Any]]:
    raw_tools: Any = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("tools"), list):
            raw_tools = payload.get("tools")
        elif isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("tools"), list):
            raw_tools = payload["result"]["tools"]
        elif isinstance(payload.get("result"), list):
            raw_tools = payload.get("result")
    elif hasattr(payload, "tools"):
        raw_tools = getattr(payload, "tools")
    elif hasattr(payload, "model_dump"):
        try:
            dumped = payload.model_dump()  # type: ignore[attr-defined]
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            if isinstance(dumped.get("tools"), list):
                raw_tools = dumped.get("tools")
            elif isinstance(dumped.get("result"), dict) and isinstance(dumped["result"].get("tools"), list):
                raw_tools = dumped["result"]["tools"]
            elif isinstance(dumped.get("result"), list):
                raw_tools = dumped.get("result")

    if not isinstance(raw_tools, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_tools:
        normalized_item = _normalize_tool_descriptor(item)
        if not normalized_item:
            continue
        tool_name = str(normalized_item.get("name") or "").strip()
        if not tool_name or tool_name in seen_names:
            continue
        seen_names.add(tool_name)
        normalized.append(normalized_item)
    return normalized


class ToolAdapter(Protocol):
    runtime_domain: str

    def is_available(self) -> bool:
        ...

    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


@dataclass
class ToolExecutionResult:
    handled: bool
    success: bool
    data: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    should_fallback: bool = False


class ToolStdioAdapter:
    """Minimal stdio tool adapter backed by tool client."""
    _PROJECT_PATH_BOOTSTRAP_TOOLS: set[str] = set()

    def __init__(
        self,
        *,
        command: str,
        args: Optional[list[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        runtime_domain: str = "backend",
    ) -> None:
        self.command = str(command or "").strip()
        self.args = [str(item) for item in (args or [])]
        self.cwd = cwd
        self.env = dict(env or {})
        self.timeout = max(5, int(timeout))
        self.runtime_domain = str(runtime_domain or "backend").strip().lower() or "backend"
        self._availability_checked = False
        self._available = False
        self._availability_reason: Optional[str] = None

    def is_available(self) -> bool:
        if self._availability_checked:
            return self._available

        if not self.command:
            self._available = False
            self._availability_reason = "missing_stdio_command"
            self._availability_checked = True
            return False

        executable = self.command
        if os.path.isabs(executable):
            exists = os.path.isfile(executable) and os.access(executable, os.X_OK)
        else:
            exists = shutil.which(executable) is not None

        self._available = bool(exists)
        self._availability_reason = None if exists else "command_not_found"
        self._availability_checked = True
        return self._available

    @property
    def availability_reason(self) -> Optional[str]:
        if not self._availability_checked:
            self.is_available()
        return self._availability_reason

    def _build_transport(self) -> StdioTransport:
        if not self.command:
            raise RuntimeError("missing_stdio_command")
        return StdioTransport(
            command=self.command,
            args=self.args,
            cwd=self.cwd,
            env=self.env,
            keep_alive=False,
        )

    @staticmethod
    def _unwrap_tool_response(result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result

        for attr in ("structuredContent", "data"):
            value = getattr(result, attr, None)
            if isinstance(value, dict):
                return value

        dumped = None
        if hasattr(result, "model_dump"):
            try:
                dumped = result.model_dump()  # type: ignore[attr-defined]
            except Exception:
                dumped = None
        if isinstance(dumped, dict):
            structured = dumped.get("structuredContent")
            if isinstance(structured, dict):
                return structured
            data = dumped.get("data")
            if isinstance(data, dict):
                return data
            content = dumped.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if isinstance(part.get("structuredContent"), dict):
                        return part["structuredContent"]
                    if isinstance(part.get("data"), dict):
                        return part["data"]
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return {"success": True, "data": text}
            return dumped

        return {"success": True, "data": str(result)}

    @staticmethod
    def _stringify_payload_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    @classmethod
    def _extract_error_text_from_payload(cls, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        for key in ("error", "message", "detail", "data", "result"):
            text = cls._stringify_payload_value(payload.get(key)).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _is_project_path_not_set_text(text: str) -> bool:
        _ = text
        return False

    @classmethod
    def _should_bootstrap_for_tool(cls, tool_name: str, text: str) -> bool:
        _ = tool_name, text
        return False

    def _resolve_project_root_for_bootstrap(self, arguments: Dict[str, Any]) -> Optional[str]:
        for key in ("project_root", "project_path", "root"):
            candidate = str(arguments.get(key) or "").strip()
            if candidate and os.path.isabs(candidate):
                return os.path.normpath(candidate)

        cwd = str(self.cwd or "").strip()
        if cwd:
            return os.path.normpath(cwd)

        candidate_path = str(arguments.get("path") or "").strip()
        if candidate_path and os.path.isabs(candidate_path):
            return os.path.normpath(candidate_path)
        return None

    async def _bootstrap_project_path(self, client: MCPClient, project_root: str) -> bool:
        candidates = (
            {"path": project_root},
            {"project_path": project_root},
            {"project_root": project_root},
            {"directory": project_root},
            {"root": project_root},
        )
        for payload in candidates:
            try:
                raw = await client.call_tool("set_project_path", payload)
            except Exception:
                continue
            normalized = self._unwrap_tool_response(raw)
            if not isinstance(normalized, dict):
                return True
            success_flag = bool(normalized.get("success", True))
            if success_flag:
                return True
            error_text = self._extract_error_text_from_payload(normalized)
            if not error_text:
                return True
            lowered = error_text.lower()
            if "already set" in lowered or "already initialized" in lowered:
                return True
        return False

    async def list_tools(self) -> List[Dict[str, Any]]:
        transport = self._build_transport()
        async with MCPClient(transport=transport, timeout=self.timeout) as client:
            list_tools = getattr(client, "list_tools", None)
            if not callable(list_tools):
                raise RuntimeError("list_tools_not_supported")
            raw_tools = await list_tools()
        return _normalize_tools_payload(raw_tools)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload_args = dict(arguments or {})
        transport = self._build_transport()
        async with MCPClient(transport=transport, timeout=self.timeout) as client:
            pre_bootstrap_needed = self._should_bootstrap_for_tool(tool_name, "")
            if pre_bootstrap_needed:
                project_root = self._resolve_project_root_for_bootstrap(payload_args)
                if project_root:
                    await self._bootstrap_project_path(client, project_root)
            try:
                raw_result = await client.call_tool(tool_name, payload_args)
            except Exception as exc:
                should_bootstrap = self._should_bootstrap_for_tool(tool_name, str(exc))
                if not should_bootstrap:
                    raise
                project_root = self._resolve_project_root_for_bootstrap(payload_args)
                if not project_root:
                    raise
                bootstrapped = await self._bootstrap_project_path(client, project_root)
                if not bootstrapped:
                    raise
                raw_result = await client.call_tool(tool_name, payload_args)

            payload = self._unwrap_tool_response(raw_result)
            needs_bootstrap = self._should_bootstrap_for_tool(
                tool_name,
                self._extract_error_text_from_payload(payload),
            )
            if needs_bootstrap:
                project_root = self._resolve_project_root_for_bootstrap(payload_args)
                if project_root and await self._bootstrap_project_path(client, project_root):
                    retried = await client.call_tool(tool_name, payload_args)
                    payload = self._unwrap_tool_response(retried)

        if not isinstance(payload, dict):
            return {"success": False, "error": "invalid_payload"}
        return payload


class ToolHttpAdapter:
    """HTTP tool adapter for streamable tool endpoint bridges."""

    def __init__(
        self,
        *,
        url: str,
        timeout: int = 30,
        runtime_domain: str = "backend",
        headers: Optional[Dict[str, str]] = None,
        synthetic_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.url = str(url or "").strip()
        self.timeout = max(5, int(timeout))
        self.runtime_domain = str(runtime_domain or "backend").strip().lower() or "backend"
        self.headers = dict(headers or {})
        self.synthetic_tools = _normalize_tools_payload(list(synthetic_tools or []))
        self._availability_checked = False
        self._available = False
        self._availability_reason: Optional[str] = None

    def _candidate_urls(self) -> List[str]:
        endpoint = str(self.url or "").strip()
        if not endpoint:
            return []
        candidates: List[str] = [endpoint]
        parsed = urlparse(endpoint)
        path = str(parsed.path or "").strip()
        if path.endswith("/mcp"):
            parent = path[: -len("/mcp")].rstrip("/")
            alt = urlunparse(parsed._replace(path=parent or "", params="", query="", fragment=""))
            if alt and alt not in candidates:
                candidates.append(alt)
        elif path in {"", "/"}:
            alt = urlunparse(parsed._replace(path="/mcp", params="", query="", fragment=""))
            if alt and alt not in candidates:
                candidates.append(alt)
        return candidates

    def _candidate_health_urls(self) -> List[str]:
        health_urls: List[str] = []
        for candidate_url in self._candidate_urls():
            parsed = urlparse(candidate_url)
            path = str(parsed.path or "").strip()
            if path.endswith("/mcp"):
                health_path = f"{path[: -len('/mcp')].rstrip('/') or ''}/health"
            elif path in {"", "/"}:
                health_path = "/health"
            else:
                health_path = f"{path.rstrip('/')}/health"
            health_url = urlunparse(parsed._replace(path=health_path, params="", query="", fragment=""))
            if health_url not in health_urls:
                health_urls.append(health_url)
        return health_urls

    @staticmethod
    def _normalize_tool_payload(data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            if "success" in data:
                return data
            if "data" in data and "error" in data:
                return data
            if "result" in data:
                return {"success": True, "data": data.get("result"), "metadata": data.get("metadata")}
            return {"success": True, "data": data}
        return {"success": True, "data": data}

    @staticmethod
    def _is_transport_error_text(error_text: str) -> bool:
        text = str(error_text or "").strip().lower()
        if not text:
            return False
        transport_tokens = (
            "server disconnected without sending a response",
            "remoteprotocolerror",
            "connecterror",
            "connection refused",
            "connection reset",
            "session terminated",
            "timed out",
            "timeout",
            "404 not found",
            "503 service unavailable",
            "502 bad gateway",
            "gateway timeout",
            "connection closed",
            "400 bad request",
            "client error '400 bad request'",
            "status_400",
        )
        return any(token in text for token in transport_tokens)

    def _resolve_project_root_for_bootstrap(self, arguments: Dict[str, Any]) -> Optional[str]:
        for key in ("project_root", "project_path", "root"):
            candidate = str(arguments.get(key) or "").strip()
            if candidate and os.path.isabs(candidate):
                return os.path.normpath(candidate)
        candidate_path = str(arguments.get("path") or "").strip()
        if candidate_path and os.path.isabs(candidate_path):
            return os.path.normpath(candidate_path)
        for header_key in (
            "Mcp-Project-Path",
            "mcp-project-path",
            "X-Mcp-Project-Path",
            "x-mcp-project-path",
        ):
            header_value = str(self.headers.get(header_key) or "").strip()
            if header_value and os.path.isabs(header_value):
                return os.path.normpath(header_value)
        return None

    async def _bootstrap_project_path(self, client: MCPClient, project_root: str) -> bool:
        candidates = (
            {"path": project_root},
            {"project_path": project_root},
            {"project_root": project_root},
            {"directory": project_root},
            {"root": project_root},
        )
        for payload in candidates:
            try:
                raw = await client.call_tool("set_project_path", payload)
            except Exception:
                continue
            normalized = ToolStdioAdapter._unwrap_tool_response(raw)
            if not isinstance(normalized, dict):
                return True
            success_flag = bool(normalized.get("success", True))
            if success_flag:
                return True
            error_text = ToolStdioAdapter._extract_error_text_from_payload(normalized)
            if not error_text:
                return True
            lowered = error_text.lower()
            if "already set" in lowered or "already initialized" in lowered:
                return True
        return False

    def is_available(self) -> bool:
        if self._availability_checked:
            return self._available
        ready, reason = probe_endpoint_readiness(
            self.url,
            timeout=max(1.0, min(float(self.timeout), 3.0)),
            headers=self.headers,
        )
        self._available = bool(ready)
        self._availability_reason = None if ready else reason
        self._availability_checked = True
        return bool(ready)

    @property
    def availability_reason(self) -> Optional[str]:
        if not self._availability_checked:
            self.is_available()
        return self._availability_reason

    def _build_http_client(self, *, candidate_url: str, transport: StreamableHttpTransport) -> MCPClient:
        try:
            return MCPClient(transport=transport, timeout=self.timeout)
        except TypeError as exc:
            message = str(exc or "")
            if "unexpected keyword argument 'transport'" not in message:
                raise
            return MCPClient(candidate_url, timeout=self.timeout)

    async def list_tools(self) -> List[Dict[str, Any]]:
        candidate_urls = self._candidate_urls()
        if not candidate_urls:
            raise RuntimeError("missing_endpoint")

        request_headers = {"content-type": "application/json", **self.headers}
        last_exc: Optional[BaseException] = None

        for candidate_url in candidate_urls:
            try:
                transport = StreamableHttpTransport(
                    candidate_url,
                    headers=self.headers or None,
                )
                client_context = self._build_http_client(
                    candidate_url=candidate_url,
                    transport=transport,
                )
                async with client_context as client:
                    list_tools = getattr(client, "list_tools", None)
                    if not callable(list_tools):
                        raise RuntimeError("list_tools_not_supported")
                    raw_tools = await list_tools()
                normalized = _normalize_tools_payload(raw_tools)
                if self.synthetic_tools:
                    normalized = _normalize_tools_payload(normalized + self.synthetic_tools)
                if normalized:
                    return normalized
            except Exception as runtime_exc:
                if not self._is_transport_error_text(str(runtime_exc)):
                    raise
                last_exc = runtime_exc

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(candidate_url, json=payload, headers=request_headers)
                    response.raise_for_status()
                    data = response.json()
                normalized = _normalize_tools_payload(data)
                if self.synthetic_tools:
                    normalized = _normalize_tools_payload(normalized + self.synthetic_tools)
                if normalized:
                    return normalized
                last_exc = RuntimeError("tools_list_empty")
            except Exception as bridge_exc:
                last_exc = bridge_exc
                continue

        if isinstance(last_exc, Exception):
            raise last_exc
        raise RuntimeError("http_list_tools_failed")

    async def _call_health_status(self) -> Dict[str, Any]:
        last_error = "healthcheck_failed"
        for candidate_url in self._candidate_health_urls():
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(candidate_url, headers=self.headers or None)
                    response.raise_for_status()
                    payload = response.json()
                status_value = str((payload or {}).get("status") or "").strip().lower()
                success = status_value in {"healthy", "ready", "ok"}
                return {
                    "success": success,
                    "data": payload,
                    "error": None if success else f"health_status:{status_value or 'unknown'}",
                }
            except Exception as exc:
                last_error = f"healthcheck_failed:{exc}"
                continue
        return {"success": False, "error": last_error}

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        normalized_tool_name = str(tool_name or "").strip().lower()
        if normalized_tool_name == "health_status":
            return await self._call_health_status()

        payload_args = dict(arguments or {})
        candidate_urls = self._candidate_urls()
        if not candidate_urls:
            raise RuntimeError("missing_endpoint")

        request_headers = {"content-type": "application/json", **self.headers}
        last_exc: Optional[BaseException] = None

        for candidate_url in candidate_urls:
            # Preferred: use official tool HTTP transport.
            try:
                transport = StreamableHttpTransport(
                    candidate_url,
                    headers=self.headers or None,
                )
                client_context = self._build_http_client(
                    candidate_url=candidate_url,
                    transport=transport,
                )
                async with client_context as client:
                    pre_bootstrap_needed = ToolStdioAdapter._should_bootstrap_for_tool(
                        tool_name,
                        "",
                    )
                    if pre_bootstrap_needed:
                        project_root = self._resolve_project_root_for_bootstrap(payload_args)
                        if project_root:
                            await self._bootstrap_project_path(client, project_root)
                    try:
                        raw_result = await client.call_tool(tool_name, payload_args)
                    except Exception as exc:
                        should_bootstrap = ToolStdioAdapter._should_bootstrap_for_tool(
                            tool_name,
                            str(exc),
                        )
                        if not should_bootstrap:
                            raise
                        project_root = self._resolve_project_root_for_bootstrap(payload_args)
                        if not project_root:
                            raise
                        bootstrapped = await self._bootstrap_project_path(client, project_root)
                        if not bootstrapped:
                            raise
                        raw_result = await client.call_tool(tool_name, payload_args)
                data = ToolStdioAdapter._unwrap_tool_response(raw_result)
                needs_bootstrap = ToolStdioAdapter._should_bootstrap_for_tool(
                    tool_name,
                    ToolStdioAdapter._extract_error_text_from_payload(data),
                )
                if needs_bootstrap:
                    project_root = self._resolve_project_root_for_bootstrap(payload_args)
                    if project_root:
                        transport_retry = StreamableHttpTransport(
                            candidate_url,
                            headers=self.headers or None,
                        )
                        retry_context = self._build_http_client(
                            candidate_url=candidate_url,
                            transport=transport_retry,
                        )
                        async with retry_context as retry_client:
                            bootstrapped = await self._bootstrap_project_path(retry_client, project_root)
                            if bootstrapped:
                                retried = await retry_client.call_tool(tool_name, payload_args)
                                data = ToolStdioAdapter._unwrap_tool_response(retried)
                return self._normalize_tool_payload(data)
            except Exception as runtime_exc:
                if not self._is_transport_error_text(str(runtime_exc)):
                    raise
                last_exc = runtime_exc

            # Backward-compatible fallback: plain JSON bridge and JSON-RPC call form.
            payload_variants = [
                {"tool": tool_name, "arguments": payload_args},
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": payload_args},
                },
            ]
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    for payload in payload_variants:
                        try:
                            response = await client.post(candidate_url, json=payload, headers=request_headers)
                            response.raise_for_status()
                            data = response.json()
                        except Exception as bridge_exc:
                            last_exc = bridge_exc
                            continue
                        if isinstance(data, dict) and "result" in data and "jsonrpc" in data:
                            data = data.get("result")
                        return self._normalize_tool_payload(data)
            except Exception as bridge_outer_exc:
                last_exc = bridge_outer_exc
                continue

        if isinstance(last_exc, Exception):
            raise last_exc
        raise RuntimeError("http_call_failed")


@dataclass
class _AdapterSelection:
    adapter_key: str
    adapter_name: str
    adapter: ToolAdapter
    runtime_domain: str
    fallback_from: Optional[str] = None


class ToolRuntime:
    _VALID_RUNTIME_MODES = {
        "backend_only",
        "sandbox_only",
        "prefer_backend",
        "prefer_sandbox",
        "backend_then_sandbox",
        "sandbox_then_backend",
        "stdio_only",
    }
    _FILESYSTEM_ANCHORED_TOOLS = {
        "list_directory",
        "list_directory_with_sizes",
        "directory_tree",
        "search_files",
        "read_file",
        "read_text_file",
        "read_media_file",
        "read_multiple_files",
        "get_file_info",
    }
    _FILESYSTEM_PATH_KEYS = {"path", "directory", "file_path", "source", "destination"}
    _FILESYSTEM_PATH_LIST_KEYS = {"paths", "files"}

    def __init__(
        self,
        *,
        enabled: bool,
        prefer_runtime: bool = True,
        router: Optional[ToolRouter] = None,
        adapters: Optional[Dict[str, ToolAdapter]] = None,
        domain_adapters: Optional[Dict[str, Dict[str, ToolAdapter]]] = None,
        runtime_modes: Optional[Dict[str, str]] = None,
        required_adapters: Optional[List[str]] = None,
        write_scope_guard: Optional[TaskWriteScopeGuard] = None,
        adapter_failure_threshold: int = 2,
        default_runtime_mode: str = "stdio_only",
        strict_mode: bool = False,
        allow_filesystem_writes: bool = True,
        project_root: Optional[str] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.prefer_runtime = bool(prefer_runtime)
        self.strict_mode = bool(strict_mode)
        self.router = router or ToolRouter()
        self.adapters: Dict[str, ToolAdapter] = dict(adapters or {})
        self.domain_adapters: Dict[str, Dict[str, ToolAdapter]] = {}
        for adapter_name, domain_map in (domain_adapters or {}).items():
            normalized_name = str(adapter_name or "").strip()
            if not normalized_name:
                continue
            if not isinstance(domain_map, dict):
                continue
            normalized_domains: Dict[str, ToolAdapter] = {}
            for domain_name, adapter in domain_map.items():
                domain_key = str(domain_name or "").strip().lower()
                if not domain_key or adapter is None:
                    continue
                normalized_domains[domain_key] = adapter
            if normalized_domains:
                self.domain_adapters[normalized_name] = normalized_domains
        self.default_runtime_mode = self._normalize_runtime_mode(default_runtime_mode)
        self.runtime_modes: Dict[str, str] = {
            str(name): self._normalize_runtime_mode(mode)
            for name, mode in (runtime_modes or {}).items()
            if str(name).strip()
        }
        self.required_adapters: List[str] = [
            str(name).strip()
            for name in (required_adapters or [])
            if str(name).strip()
        ]
        self.write_scope_guard = write_scope_guard
        self.adapter_failure_threshold = max(1, int(adapter_failure_threshold or 2))
        self.allow_filesystem_writes = bool(allow_filesystem_writes)
        normalized_project_root = str(project_root or "").strip()
        if normalized_project_root and os.path.isabs(normalized_project_root):
            self.project_root = os.path.normpath(normalized_project_root)
        else:
            self.project_root = None
        self._adapter_failure_counts: Dict[str, int] = {}
        self._adapter_disabled: Dict[str, bool] = {}
        self._retrieval_cache: Dict[str, Dict[str, Any]] = {}
        self._retrieval_cache_hits = 0
        self._retrieval_cache_misses = 0
        self._retrieval_cache_tools = {"read_file", "search_code"}

    @staticmethod
    def _path_within_root(path_value: str, root_value: str) -> bool:
        try:
            return os.path.commonpath([os.path.normpath(path_value), os.path.normpath(root_value)]) == os.path.normpath(
                root_value
            )
        except Exception:
            return False

    def _anchor_path_to_project_root(self, value: Any) -> Any:
        if not self.project_root:
            return value
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text or text in {".", "./", "..", "../"}:
            return self.project_root
        expanded = os.path.expanduser(text)
        if os.path.isabs(expanded):
            return os.path.normpath(expanded)
        candidate = os.path.normpath(os.path.join(self.project_root, expanded))
        if not self._path_within_root(candidate, self.project_root):
            return self.project_root
        return candidate

    def _normalize_filesystem_arguments(self, route: ToolRoute) -> Dict[str, Any]:
        arguments = dict(route.arguments or {})
        if not self.project_root:
            return arguments
        normalized_tool = str(route.tool_name or "").strip().lower()
        if normalized_tool not in self._FILESYSTEM_ANCHORED_TOOLS:
            return arguments

        for key in self._FILESYSTEM_PATH_KEYS:
            if key in arguments:
                arguments[key] = self._anchor_path_to_project_root(arguments.get(key))
        for key in self._FILESYSTEM_PATH_LIST_KEYS:
            raw_value = arguments.get(key)
            if isinstance(raw_value, list):
                arguments[key] = [self._anchor_path_to_project_root(item) for item in raw_value]

        if "path" not in arguments and "directory" not in arguments:
            arguments["path"] = self.project_root
        return arguments

    def _prepare_route(self, route: ToolRoute) -> ToolRoute:
        adapter_name = str(route.adapter_name or "").strip().lower()
        if adapter_name == "filesystem":
            normalized_arguments = self._normalize_filesystem_arguments(route)
        else:
            return route
        if normalized_arguments == route.arguments:
            return route
        return ToolRoute(
            adapter_name=route.adapter_name,
            tool_name=route.tool_name,
            arguments=normalized_arguments,
            is_write=route.is_write,
        )

    @classmethod
    def _normalize_runtime_mode(cls, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in cls._VALID_RUNTIME_MODES:
            return mode
        return "stdio_only"

    def _get_runtime_mode(self, adapter_name: str) -> str:
        normalized = str(adapter_name or "").strip()
        if normalized in self.runtime_modes:
            return self.runtime_modes[normalized]
        return self.default_runtime_mode

    @staticmethod
    def _candidate_domains_for_mode(mode: str) -> List[str]:
        mode_value = str(mode or "").strip().lower()
        if mode_value == "backend_only":
            return ["backend"]
        if mode_value == "sandbox_only":
            return ["sandbox"]
        if mode_value == "stdio_only":
            return ["backend"]
        if mode_value in {"prefer_backend", "backend_then_sandbox"}:
            return ["backend", "sandbox"]
        if mode_value in {"prefer_sandbox", "sandbox_then_backend"}:
            return ["sandbox", "backend"]
        return ["backend", "sandbox"]

    @staticmethod
    def _adapter_runtime_domain(adapter: ToolAdapter) -> str:
        value = getattr(adapter, "runtime_domain", None)
        domain = str(value or "").strip().lower()
        return domain or "backend"

    @staticmethod
    def _adapter_available(adapter: ToolAdapter) -> Tuple[bool, Optional[str]]:
        checker = getattr(adapter, "is_available", None)
        if callable(checker):
            try:
                available = bool(checker())
            except Exception as exc:
                return False, f"is_available_error:{exc}"
            if available:
                return True, None
            reason = getattr(adapter, "availability_reason", None)
            reason_text = str(reason or "").strip() or "adapter_unavailable"
            return False, reason_text
        return True, None

    @staticmethod
    def _fallback_allowed_for_adapter(adapter_name: str) -> bool:
        _ = adapter_name
        return True

    @staticmethod
    def _failure_mode_for_adapter(adapter_name: str) -> Optional[str]:
        return None

    @staticmethod
    def _is_infra_error(error_text: str, *, tool_name: Optional[str] = None) -> bool:
        text = str(error_text or "").lower()
        if not text:
            return False
        normalized_tool = str(tool_name or "").strip().lower()

        transport_tokens = (
            "adapter unavailable",
            "missing_stdio_command",
            "command_not_found",
            "adapter_unavailable",
            "healthcheck_failed",
            "server disconnected without sending a response",
            "remoteprotocolerror",
            "connecterror",
            "readtimeout",
            "connect timeout",
            "connection reset",
            "connection refused",
            "status_502",
            "status_503",
            "status_504",
            " 502 ",
            " 503 ",
            " 504 ",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "command not found",
        )
        if any(token in text for token in transport_tokens):
            return True

        file_input_error_tokens = (
            "no such file or directory",
            "enoent",
            "file not found",
            "文件不存在",
            "路径不存在",
        )
        if any(token in text for token in file_input_error_tokens):
            input_sensitive_tools = {
                "read_file",
                "write_file",
                "edit_file",
                "search_files",
            }
            if normalized_tool in input_sensitive_tools:
                return False
            if "project path not set" in text:
                return True
            return True

        return False

    @staticmethod
    def _is_expected_qmd_verify_error(
        *,
        adapter_name: str,
        agent_name: Optional[str],
        error_text: str,
    ) -> bool:
        _ = adapter_name
        _ = agent_name
        _ = error_text
        return False

    def _register_adapter_failure(self, adapter_key: str) -> None:
        key = str(adapter_key or "").strip()
        if not key:
            return
        next_count = self._adapter_failure_counts.get(key, 0) + 1
        self._adapter_failure_counts[key] = next_count
        if next_count >= self.adapter_failure_threshold:
            self._adapter_disabled[key] = True

    def _clear_adapter_failure(self, adapter_key: str) -> None:
        key = str(adapter_key or "").strip()
        if not key:
            return
        self._adapter_failure_counts.pop(key, None)
        self._adapter_disabled.pop(key, None)

    def _is_adapter_disabled(self, adapter_key: str) -> bool:
        return bool(self._adapter_disabled.get(str(adapter_key or "").strip()))

    def _resolve_adapter(self, route: ToolRoute) -> Tuple[Optional[_AdapterSelection], str]:
        adapter_name = str(route.adapter_name or "").strip()
        if not adapter_name:
            return None, "adapter_unavailable"

        domain_map = self.domain_adapters.get(adapter_name)
        if domain_map:
            mode = self._get_runtime_mode(adapter_name)
            domains = self._candidate_domains_for_mode(mode)
            primary_domain = domains[0] if domains else None
            candidate_count = 0
            disabled_count = 0
            for domain in domains:
                adapter = domain_map.get(domain)
                if adapter is None:
                    continue
                candidate_count += 1
                adapter_key = f"{adapter_name}:{domain}"
                if self._is_adapter_disabled(adapter_key):
                    disabled_count += 1
                    continue
                available, reason = self._adapter_available(adapter)
                if not available:
                    if reason and self._is_infra_error(reason):
                        self._register_adapter_failure(adapter_key)
                    continue
                return (
                    _AdapterSelection(
                        adapter_key=adapter_key,
                        adapter_name=adapter_name,
                        adapter=adapter,
                        runtime_domain=domain,
                        fallback_from=primary_domain if primary_domain and primary_domain != domain else None,
                    ),
                    "",
                )
            if candidate_count > 0 and disabled_count >= candidate_count:
                return None, "adapter_disabled_after_failures"
            return None, "adapter_unavailable"

        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            return None, "adapter_unavailable"

        adapter_domain = self._adapter_runtime_domain(adapter)
        adapter_key = (
            adapter_name
            if adapter_domain == "backend"
            else f"{adapter_name}:{adapter_domain}"
        )
        if self._is_adapter_disabled(adapter_key):
            return None, "adapter_disabled_after_failures"
        available, reason = self._adapter_available(adapter)
        if not available:
            if reason and self._is_infra_error(reason):
                self._register_adapter_failure(adapter_key)
            if reason == "command_not_found":
                return None, "command_not_found"
            return None, "adapter_unavailable"

        return (
            _AdapterSelection(
                adapter_key=adapter_key,
                adapter_name=adapter_name,
                adapter=adapter,
                runtime_domain=adapter_domain,
            ),
            "",
        )

    def _required_adapter_names(self) -> List[str]:
        if self.required_adapters:
            return list(dict.fromkeys(self.required_adapters))
        inferred = list(self.adapters.keys()) + list(self.domain_adapters.keys())
        return list(dict.fromkeys(inferred))

    def _resolve_adapter_selection(self, adapter_name: str) -> Tuple[Optional[_AdapterSelection], str]:
        normalized_name = str(adapter_name or "").strip()
        if not normalized_name:
            return None, "adapter_unavailable"
        pseudo_route = ToolRoute(
            adapter_name=normalized_name,
            tool_name="tools/list",
            arguments={},
            is_write=False,
        )
        return self._resolve_adapter(pseudo_route)

    async def list_adapter_tools(self, adapter_name: str) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "success": False,
                "adapter_name": str(adapter_name or "").strip(),
                "tools": [],
                "error": "runtime_disabled",
                "metadata": {"runtime_used": False},
            }

        normalized_name = str(adapter_name or "").strip()
        selection, skip_reason = self._resolve_adapter_selection(normalized_name)
        if selection is None:
            return {
                "success": False,
                "adapter_name": normalized_name,
                "tools": [],
                "error": f"adapter_unavailable:{normalized_name or 'unknown'}",
                "metadata": {
                    "runtime_used": True,
                    "runtime_adapter": normalized_name or None,
                    "runtime_tool": "tools/list",
                    "runtime_skipped": True,
                    "runtime_skip_reason": skip_reason or "adapter_unavailable",
                },
            }

        try:
            tools = await selection.adapter.list_tools()
        except Exception as exc:
            error_text = f"{exc}"
            if self._is_infra_error(error_text, tool_name="tools/list"):
                self._register_adapter_failure(selection.adapter_key)
            return {
                "success": False,
                "adapter_name": normalized_name,
                "tools": [],
                "error": f"list_tools_failed:{exc}",
                "metadata": {
                    "runtime_used": True,
                    "runtime_adapter": selection.adapter_name,
                    "runtime_tool": "tools/list",
                    "runtime_domain": selection.runtime_domain,
                    "runtime_fallback_used": bool(selection.fallback_from),
                    "runtime_fallback_from": selection.fallback_from,
                    "runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                    "runtime_skipped": False,
                },
            }

        self._clear_adapter_failure(selection.adapter_key)
        return {
            "success": True,
            "runtime_name": normalized_name,
            "tools": _normalize_tools_payload(tools),
            "error": None,
            "metadata": {
                "runtime_used": True,
                "runtime_adapter": selection.adapter_name,
                "runtime_tool": "tools/list",
                "runtime_domain": selection.runtime_domain,
                "runtime_fallback_used": bool(selection.fallback_from),
                "runtime_fallback_from": selection.fallback_from,
                "runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                "runtime_skipped": False,
            },
        }

    async def call_adapter_tool(
        self,
        *,
        adapter_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_name: Optional[str] = None,
        alias_used: Optional[str] = None,
    ) -> ToolExecutionResult:
        if not self.enabled:
            return ToolExecutionResult(handled=False, success=False)

        normalized_adapter = str(adapter_name or "").strip()
        normalized_tool = str(tool_name or "").strip()
        if not normalized_adapter or not normalized_tool:
            return ToolExecutionResult(
                handled=True,
                success=False,
                error="invalid_adapter_tool",
                metadata={
                    "runtime_used": True,
                    "runtime_adapter": normalized_adapter or None,
                    "runtime_tool": normalized_tool or None,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "runtime_skipped": True,
                    "runtime_skip_reason": "invalid_tool",
                },
                should_fallback=False,
            )

        pseudo_route = ToolRoute(
            adapter_name=normalized_adapter,
            tool_name=normalized_tool,
            arguments=dict(arguments or {}),
            is_write=False,
        )
        selection, skip_reason = self._resolve_adapter(pseudo_route)
        if selection is None:
            mapped_reason = skip_reason or "adapter_unavailable"
            return ToolExecutionResult(
                handled=True,
                success=False,
                error=f"adapter_unavailable:{normalized_adapter}",
                metadata={
                    "runtime_used": True,
                    "runtime_adapter": normalized_adapter,
                    "runtime_tool": normalized_tool,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "runtime_skipped": True,
                    "runtime_skip_reason": mapped_reason,
                },
                should_fallback=self._fallback_allowed_for_adapter(normalized_adapter),
            )

        try:
            payload = await selection.adapter.call_tool(normalized_tool, pseudo_route.arguments)
        except Exception as exc:
            error_text = f"{exc}"
            if self._is_expected_qmd_verify_error(
                adapter_name=normalized_adapter,
                agent_name=agent_name,
                error_text=error_text,
            ):
                logger.info(
                    "Tool runtime direct tool call expected failure (%s/%s): %s",
                    normalized_adapter,
                    normalized_tool,
                    exc,
                )
            else:
                logger.warning(
                    "Tool runtime direct tool call failed (%s/%s): %s",
                    normalized_adapter,
                    normalized_tool,
                    exc,
                )
            if self._is_infra_error(error_text, tool_name=normalized_tool):
                self._register_adapter_failure(selection.adapter_key)
            return ToolExecutionResult(
                handled=True,
                success=False,
                error=f"call_failed:{exc}",
                metadata={
                    "runtime_used": True,
                    "runtime_adapter": selection.adapter_name,
                    "runtime_tool": normalized_tool,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "runtime_domain": selection.runtime_domain,
                    "runtime_fallback_used": bool(selection.fallback_from),
                    "runtime_fallback_from": selection.fallback_from,
                    "runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                    "runtime_skipped": False,
                },
                should_fallback=self._fallback_allowed_for_adapter(selection.adapter_name),
            )

        success_flag = bool(payload.get("success", True))
        error_text = str(payload.get("error") or "").strip() or None
        output_data = payload.get("data", payload.get("result", payload))
        output_text = self._stringify_data(output_data)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        merged_metadata = {
            **metadata,
            "runtime_used": True,
            "runtime_adapter": selection.adapter_name,
            "runtime_tool": normalized_tool,
            "agent": agent_name,
            "alias_used": alias_used,
            "runtime_domain": selection.runtime_domain,
            "runtime_fallback_used": bool(selection.fallback_from),
            "runtime_fallback_from": selection.fallback_from,
            "runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
            "runtime_skipped": False,
        }
        if not success_flag and not error_text:
            error_text = "tool_failed"
        if not success_flag and self._is_infra_error(error_text or "", tool_name=normalized_tool):
            self._register_adapter_failure(selection.adapter_key)
        if success_flag:
            self._clear_adapter_failure(selection.adapter_key)

        return ToolExecutionResult(
            handled=True,
            success=success_flag,
            data=output_text,
            error=error_text,
            metadata=merged_metadata,
            should_fallback=(
                (not success_flag)
                and self._fallback_allowed_for_adapter(selection.adapter_name)
            ),
        )

    def can_handle(self, tool_name: str) -> bool:
        if not self.enabled:
            return False
        route = self.router.route(tool_name, {})
        if not route:
            return False
        normalized_adapter = str(route.adapter_name or "").strip()
        if not normalized_adapter:
            return False
        if normalized_adapter in self.adapters:
            return True
        domain_map = self.domain_adapters.get(normalized_adapter)
        return bool(isinstance(domain_map, dict) and domain_map)

    def should_prefer_runtime(self) -> bool:
        return bool(self.enabled and self.prefer_runtime)

    def get_write_scope_guard(self) -> Optional[TaskWriteScopeGuard]:
        return self.write_scope_guard

    def register_evidence_path(self, file_path: Any) -> bool:
        if not self.write_scope_guard:
            return False
        return self.write_scope_guard.register_evidence_path(file_path)

    def register_evidence_paths(self, file_paths: list[Any]) -> int:
        if not self.write_scope_guard:
            return 0
        return self.write_scope_guard.register_evidence_paths(file_paths)

    @staticmethod
    def _normalize_fingerprint_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): ToolRuntime._normalize_fingerprint_value(value[key])
                for key in sorted(value.keys(), key=lambda item: str(item))
            }
        if isinstance(value, list):
            return [ToolRuntime._normalize_fingerprint_value(item) for item in value]
        return str(value)

    def _build_retrieval_cache_key(
        self,
        *,
        tool_name: str,
        route: ToolRoute,
    ) -> Optional[str]:
        normalized_tool = str(tool_name or "").strip().lower()
        if normalized_tool not in self._retrieval_cache_tools:
            return None
        payload = {
            "tool": normalized_tool,
            "adapter": str(route.adapter_name or "").strip().lower(),
            "runtime_tool": str(route.tool_name or "").strip().lower(),
            "arguments": self._normalize_fingerprint_value(route.arguments),
        }
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            serialized = str(payload)
        digest = hashlib.sha1(serialized.encode("utf-8", errors="ignore")).hexdigest()
        return f"{normalized_tool}:{digest}"

    def get_retrieval_cache_stats(self) -> Dict[str, int]:
        return {
            "hits": int(self._retrieval_cache_hits),
            "misses": int(self._retrieval_cache_misses),
            "size": len(self._retrieval_cache),
        }

    def _metadata_from_write_scope(
        self,
        *,
        decision: Optional[WriteScopeDecision],
    ) -> Dict[str, Any]:
        if not decision:
            return {}
        return {
            "write_scope_allowed": bool(decision.allowed),
            "write_scope_reason": decision.reason,
            "write_scope_file": decision.file_path,
            "write_scope_total_files": int(decision.total_files),
        }

    @staticmethod
    def _stringify_data(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False, indent=2)
            except Exception:
                return str(value)
        return str(value)

    @staticmethod
    def _route_label(route: Optional[ToolRoute]) -> Optional[str]:
        if route is None:
            return None
        adapter_name = str(route.adapter_name or "").strip()
        runtime_tool_name = str(route.tool_name or "").strip()
        if adapter_name and runtime_tool_name:
            return f"{adapter_name}.{runtime_tool_name}"
        if adapter_name:
            return adapter_name
        if runtime_tool_name:
            return runtime_tool_name
        return None

    @staticmethod
    def _build_search_code_route_fallback(
        *,
        tool_name: str,
        route: ToolRoute,
    ) -> Optional[ToolRoute]:
        _ = tool_name
        _ = route
        return None

    async def execute_tool(
        self,
        *,
        tool_name: str,
        tool_input: Dict[str, Any],
        agent_name: Optional[str] = None,
        alias_used: Optional[str] = None,
    ) -> ToolExecutionResult:
        if not self.enabled:
            return ToolExecutionResult(handled=False, success=False)

        normalized_tool_name = str(tool_name or "").strip().lower()
        route: Optional[ToolRoute] = self.router.route(tool_name, tool_input)
        if not route:
            return ToolExecutionResult(handled=False, success=False)
        route = self._prepare_route(route)
        primary_route = route
        fallback_route = self._build_search_code_route_fallback(
            tool_name=normalized_tool_name,
            route=primary_route,
        )
        route_primary_label = self._route_label(primary_route)
        route_fallback_label = self._route_label(fallback_route)

        write_decision: Optional[WriteScopeDecision] = None
        if (
            route.is_write
            and str(route.adapter_name or "").strip().lower() == "filesystem"
            and not self.allow_filesystem_writes
        ):
            message = "filesystem_readonly_policy"
            return ToolExecutionResult(
                handled=True,
                success=False,
                error=message,
                data=message,
                metadata={
                    "runtime_used": True,
                    "runtime_adapter": route.adapter_name,
                    "runtime_tool": route.tool_name,
                    "route_primary": route_primary_label,
                    "route_fallback": route_fallback_label,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "runtime_skipped": True,
                    "runtime_skip_reason": "filesystem_readonly_policy",
                    "filesystem_readonly": True,
                },
                should_fallback=False,
            )
        if route.is_write and self.write_scope_guard is not None:
            write_decision = self.write_scope_guard.evaluate_write_request(
                tool_name=tool_name,
                tool_input=tool_input,
            )
            if not write_decision.allowed:
                message = f"写入已拒绝: {write_decision.reason}"
                return ToolExecutionResult(
                    handled=True,
                    success=False,
                    error=message,
                    data=message,
                    metadata={
                        "runtime_used": True,
                        "runtime_adapter": route.adapter_name,
                        "runtime_tool": route.tool_name,
                        "route_primary": route_primary_label,
                        "route_fallback": route_fallback_label,
                        "agent": agent_name,
                        "alias_used": alias_used,
                        **self._metadata_from_write_scope(decision=write_decision),
                    },
                    should_fallback=False,
                )

        retrieval_cache_key = self._build_retrieval_cache_key(
            tool_name=normalized_tool_name,
            route=route,
        )
        if retrieval_cache_key:
            cached = self._retrieval_cache.get(retrieval_cache_key)
            if cached is not None:
                self._retrieval_cache_hits += 1
                cached_metadata = (
                    dict(cached.get("metadata"))
                    if isinstance(cached.get("metadata"), dict)
                    else {}
                )
                merged_cached_metadata = {
                    **cached_metadata,
                    "cache_hit": True,
                    "runtime_cache_hit": True,
                    "runtime_cache_key": retrieval_cache_key,
                    "runtime_cache_stats": self.get_retrieval_cache_stats(),
                    "route_primary": route_primary_label,
                    "route_fallback": route_fallback_label,
                }
                return ToolExecutionResult(
                    handled=True,
                    success=bool(cached.get("success")),
                    data=str(cached.get("data") or ""),
                    error=str(cached.get("error") or "").strip() or None,
                    metadata=merged_cached_metadata,
                    should_fallback=False,
                )
            self._retrieval_cache_misses += 1

        attempt_plan: List[Tuple[str, ToolRoute]] = [("primary", primary_route)]
        if fallback_route is not None:
            attempt_plan.append(("fallback", fallback_route))

        for attempt_index, (attempt_name, attempt_route) in enumerate(attempt_plan):
            is_route_fallback = attempt_name == "fallback"

            selection, skip_reason = self._resolve_adapter(attempt_route)
            if selection is None:
                if attempt_index < len(attempt_plan) - 1:
                    continue
                mapped_reason = skip_reason or "adapter_unavailable"
                failure_mode = self._failure_mode_for_adapter(attempt_route.adapter_name)
                return ToolExecutionResult(
                    handled=True,
                    success=False,
                    error=f"runtime_adapter_unavailable:{attempt_route.adapter_name}",
                    metadata={
                        "runtime_used": True,
                        "runtime_adapter": attempt_route.adapter_name,
                        "runtime_tool": attempt_route.tool_name,
                        "agent": agent_name,
                        "alias_used": alias_used,
                        "runtime_skipped": True,
                        "runtime_skip_reason": mapped_reason,
                        "runtime_failure_mode": failure_mode,
                        "runtime_cache_hit": False if retrieval_cache_key else None,
                        "runtime_fallback_used": bool(is_route_fallback),
                        "runtime_fallback_from": route_primary_label if is_route_fallback else None,
                        "runtime_fallback_to": None,
                        "route_primary": route_primary_label,
                        "route_fallback": route_fallback_label,
                        **self._metadata_from_write_scope(decision=write_decision),
                    },
                    should_fallback=self._fallback_allowed_for_adapter(attempt_route.adapter_name),
                )

            try:
                payload = await selection.adapter.call_tool(
                    attempt_route.tool_name,
                    attempt_route.arguments,
                )
            except Exception as exc:
                logger.warning(
                    "Tool runtime call failed (%s/%s): %s",
                    attempt_route.adapter_name,
                    attempt_route.tool_name,
                    exc,
                )
                error_text = f"{exc}"
                if self._is_infra_error(error_text, tool_name=attempt_route.tool_name):
                    self._register_adapter_failure(selection.adapter_key)
                if attempt_index < len(attempt_plan) - 1:
                    continue
                failure_mode = self._failure_mode_for_adapter(selection.adapter_name)
                runtime_fallback_used = bool(selection.fallback_from) or bool(is_route_fallback)
                return ToolExecutionResult(
                    handled=True,
                    success=False,
                    error=f"call_failed:{exc}",
                    metadata={
                        "runtime_used": True,
                        "runtime_adapter": selection.adapter_name,
                        "runtime_tool": attempt_route.tool_name,
                        "agent": agent_name,
                        "alias_used": alias_used,
                        "runtime_domain": selection.runtime_domain,
                        "runtime_fallback_used": runtime_fallback_used,
                        "runtime_fallback_from": (
                            selection.fallback_from
                            if selection.fallback_from
                            else (route_primary_label if is_route_fallback else None)
                        ),
                        "runtime_fallback_to": (
                            selection.runtime_domain if runtime_fallback_used else None
                        ),
                        "route_primary": route_primary_label,
                        "route_fallback": route_fallback_label,
                        "runtime_skipped": False,
                        "runtime_failure_mode": failure_mode,
                        "runtime_cache_hit": False if retrieval_cache_key else None,
                        **self._metadata_from_write_scope(decision=write_decision),
                    },
                    should_fallback=self._fallback_allowed_for_adapter(selection.adapter_name),
                )

            success_flag = bool(payload.get("success", True))
            error_text = str(payload.get("error") or "").strip() or None
            output_data = payload.get("data", payload.get("result", payload))
            output_text = self._stringify_data(output_data)
            payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            runtime_fallback_used = bool(selection.fallback_from) or bool(is_route_fallback)
            merged_metadata = {
                **payload_metadata,
                "runtime_used": True,
                "runtime_adapter": selection.adapter_name,
                "runtime_tool": attempt_route.tool_name,
                "agent": agent_name,
                "alias_used": alias_used,
                "runtime_domain": selection.runtime_domain,
                "runtime_fallback_used": runtime_fallback_used,
                "runtime_fallback_from": (
                    selection.fallback_from
                    if selection.fallback_from
                    else (route_primary_label if is_route_fallback else None)
                ),
                "runtime_fallback_to": (
                    selection.runtime_domain if runtime_fallback_used else None
                ),
                "route_primary": route_primary_label,
                "route_fallback": route_fallback_label,
                "runtime_skipped": False,
                "runtime_failure_mode": self._failure_mode_for_adapter(selection.adapter_name),
                "runtime_cache_hit": False if retrieval_cache_key else None,
                **self._metadata_from_write_scope(decision=write_decision),
            }

            if not success_flag and not error_text:
                error_text = "runtime_tool_failed"
            if not success_flag and self._is_infra_error(
                error_text or "",
                tool_name=attempt_route.tool_name,
            ):
                self._register_adapter_failure(selection.adapter_key)

            if success_flag:
                self._clear_adapter_failure(selection.adapter_key)
                if retrieval_cache_key:
                    self._retrieval_cache[retrieval_cache_key] = {
                        "success": True,
                        "data": output_text,
                        "error": None,
                        "metadata": merged_metadata,
                    }
                    if len(self._retrieval_cache) > 2000:
                        oldest_key = next(iter(self._retrieval_cache))
                        self._retrieval_cache.pop(oldest_key, None)
                    merged_metadata = {
                        **merged_metadata,
                        "runtime_cache_key": retrieval_cache_key,
                        "runtime_cache_stats": self.get_retrieval_cache_stats(),
                    }
                return ToolExecutionResult(
                    handled=True,
                    success=True,
                    data=output_text,
                    error=None,
                    metadata=merged_metadata,
                    should_fallback=False,
                )

            if attempt_index < len(attempt_plan) - 1:
                continue

            if retrieval_cache_key:
                merged_metadata = {
                    **merged_metadata,
                    "runtime_cache_key": retrieval_cache_key,
                    "runtime_cache_stats": self.get_retrieval_cache_stats(),
                }

            return ToolExecutionResult(
                handled=True,
                success=False,
                data=output_text,
                error=error_text,
                metadata=merged_metadata,
                should_fallback=self._fallback_allowed_for_adapter(selection.adapter_name),
            )

        return ToolExecutionResult(handled=False, success=False)

    def ensure_all_adapters_ready(self, runtime_domain: str = "backend") -> Dict[str, Any]:
        domain_value = str(runtime_domain or "backend").strip().lower() or "backend"
        required = self._required_adapter_names()

        details: Dict[str, Dict[str, Any]] = {}
        not_ready: List[Dict[str, str]] = []

        for adapter_name in required:
            adapter_details: Dict[str, Any] = {"required": True, "runtime_mode": self._get_runtime_mode(adapter_name)}
            if domain_value == "all":
                domains = self._candidate_domains_for_mode(self._get_runtime_mode(adapter_name))
                if not domains:
                    domains = ["backend"]
            else:
                domains = [domain_value]
            normalized_domains: List[str] = []
            for domain in domains:
                domain_key = str(domain or "").strip().lower()
                if domain_key and domain_key not in normalized_domains:
                    normalized_domains.append(domain_key)
            domain_checks: List[Tuple[str, bool, str]] = []
            for domain in normalized_domains:
                ready, reason = self._check_adapter_ready_for_domain(adapter_name, domain)
                adapter_details[domain] = {"ready": ready, "reason": reason}
                domain_checks.append((domain, bool(ready), str(reason or "")))

            if domain_value == "all":
                ready_domains = [domain for domain, ready, _reason in domain_checks if ready]
                adapter_details["ready_domain"] = ready_domains[0] if ready_domains else None
                adapter_details["ready_domains"] = ready_domains
                if not ready_domains:
                    reason_text = "; ".join(
                        f"{domain}:{reason}"
                        for domain, _ready, reason in domain_checks
                    ) or "all_domains_unavailable"
                    not_ready.append(
                        {
                            "adapter": adapter_name,
                            "runtime_domain": "all",
                            "reason": reason_text,
                        }
                    )
            else:
                for domain, ready, reason in domain_checks:
                    if ready:
                        continue
                    not_ready.append(
                        {
                            "adapter": adapter_name,
                            "runtime_domain": domain,
                            "reason": reason,
                        }
                    )
            details[adapter_name] = adapter_details

        return {
            "ready": len(not_ready) == 0,
            "runtime_domain": domain_value,
            "required_adapters": required,
            "not_ready": not_ready,
            "details": details,
        }

    def _check_adapter_ready_for_domain(self, adapter_name: str, runtime_domain: str) -> Tuple[bool, str]:
        adapter_key = str(adapter_name or "").strip()
        domain = str(runtime_domain or "").strip().lower()
        if not adapter_key or not domain:
            return False, "invalid_runtime_domain"

        domain_map = self.domain_adapters.get(adapter_key)
        if domain_map is not None:
            adapter = domain_map.get(domain)
            if adapter is None:
                return False, "domain_adapter_missing"
            full_adapter_key = f"{adapter_key}:{domain}"
            if self._is_adapter_disabled(full_adapter_key):
                return False, "adapter_disabled_after_failures"
            available, reason = self._adapter_available(adapter)
            if not available:
                return False, reason or "adapter_unavailable"
            return True, "ready"

        adapter = self.adapters.get(adapter_key)
        if adapter is None:
            return False, "adapter_unavailable"
        adapter_domain = self._adapter_runtime_domain(adapter)
        if adapter_domain != domain:
            return False, "adapter_domain_mismatch"
        full_adapter_key = adapter_key if domain == "backend" else f"{adapter_key}:{domain}"
        if self._is_adapter_disabled(full_adapter_key):
            return False, "adapter_disabled_after_failures"
        available, reason = self._adapter_available(adapter)
        if not available:
            return False, reason or "adapter_unavailable"
        return True, "ready"
