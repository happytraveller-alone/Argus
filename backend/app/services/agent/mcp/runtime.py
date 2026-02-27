from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx
from fastmcp import Client as MCPClient
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from urllib.parse import urlparse, urlunparse

from app.core.config import settings

from .local_proxy import LocalMCPProxyAdapter
from .router import MCPToolRoute, MCPToolRouter
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


class MCPAdapter(Protocol):
    runtime_domain: str

    def is_available(self) -> bool:
        ...

    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


@dataclass
class MCPExecutionResult:
    handled: bool
    success: bool
    data: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    should_fallback: bool = False


class FastMCPStdioAdapter:
    """Minimal stdio MCP adapter backed by fastmcp.Client."""
    _PROJECT_PATH_BOOTSTRAP_TOOLS = {
        "search_code_advanced",
        "find_files",
        "refresh_index",
        "build_deep_index",
        "get_symbol_body",
        "get_file_summary",
    }
    _NPX_PACKAGE_BINARIES = {
        "@modelcontextprotocol/server-filesystem": "mcp-server-filesystem",
        "@modelcontextprotocol/server-sequential-thinking": "mcp-server-sequential-thinking",
    }
    _NPX_ONLY_FLAGS = {"-y", "--yes"}
    _NPX_PACKAGE_FLAGS = {"-p", "--package"}

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
        normalized_command, normalized_args = self._normalize_stdio_command(
            command=str(command or "").strip(),
            args=[str(item) for item in (args or [])],
        )
        self.command = normalized_command
        self.args = normalized_args
        self.cwd = cwd
        self.env = dict(env or {})
        self.timeout = max(5, int(timeout))
        self.runtime_domain = str(runtime_domain or "backend").strip().lower() or "backend"
        self._availability_checked = False
        self._available = False
        self._availability_reason: Optional[str] = None

    @classmethod
    def _normalize_stdio_command(
        cls,
        *,
        command: str,
        args: List[str],
    ) -> Tuple[str, List[str]]:
        normalized_command = str(command or "").strip()
        normalized_args = [str(item) for item in (args or [])]
        if not normalized_command:
            return normalized_command, normalized_args

        command_basename = os.path.basename(normalized_command).strip().lower()
        if command_basename not in {"npx", "npm"}:
            return normalized_command, normalized_args

        matched_package = ""
        for item in normalized_args:
            token = str(item or "").strip()
            if token in cls._NPX_PACKAGE_BINARIES:
                matched_package = token
                break
        if not matched_package:
            return normalized_command, normalized_args

        binary_name = cls._NPX_PACKAGE_BINARIES.get(matched_package)
        if not binary_name:
            return normalized_command, normalized_args
        resolved_binary = shutil.which(binary_name)
        if not resolved_binary:
            return normalized_command, normalized_args

        filtered_args: List[str] = []
        skip_next = False
        npm_exec_mode = command_basename == "npm"
        for item in normalized_args:
            token = str(item or "").strip()
            if not token:
                continue
            lowered = token.lower()
            if skip_next:
                skip_next = False
                continue
            if token == matched_package:
                continue
            if lowered in cls._NPX_ONLY_FLAGS:
                continue
            if lowered in cls._NPX_PACKAGE_FLAGS:
                skip_next = True
                continue
            if npm_exec_mode and lowered in {"exec", "x"}:
                continue
            if token == "--":
                continue
            if token == binary_name or token == resolved_binary:
                continue
            filtered_args.append(token)
        return resolved_binary, filtered_args

    def is_available(self) -> bool:
        if self._availability_checked:
            return self._available

        if not self.command:
            self._available = False
            self._availability_reason = "missing_mcp_stdio_command"
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
            raise RuntimeError("missing_mcp_stdio_command")
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
        lowered = str(text or "").lower()
        if not lowered:
            return False
        return (
            "project path not set" in lowered
            or ("set_project_path" in lowered and "project" in lowered and "path" in lowered)
        )

    @classmethod
    def _should_bootstrap_for_tool(cls, tool_name: str, text: str) -> bool:
        normalized_tool = str(tool_name or "").strip().lower()
        if not normalized_tool or normalized_tool == "set_project_path":
            return False
        if cls._is_project_path_not_set_text(text):
            return True
        return normalized_tool in cls._PROJECT_PATH_BOOTSTRAP_TOOLS

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
                raise RuntimeError("mcp_list_tools_not_supported")
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
            return {"success": False, "error": "mcp_invalid_payload"}
        return payload


class FastMCPHttpAdapter:
    """HTTP MCP adapter for streamable MCP/JSON endpoint bridges."""

    def __init__(
        self,
        *,
        url: str,
        timeout: int = 30,
        runtime_domain: str = "backend",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.url = str(url or "").strip()
        self.timeout = max(5, int(timeout))
        self.runtime_domain = str(runtime_domain or "backend").strip().lower() or "backend"
        self.headers = dict(headers or {})
        self._availability_checked = False
        self._available = False
        self._availability_reason: Optional[str] = None

    def _health_url(self) -> str:
        parsed = urlparse(self.url)
        return urlunparse(parsed._replace(path="/health", params="", query="", fragment=""))

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
            normalized = FastMCPStdioAdapter._unwrap_tool_response(raw)
            if not isinstance(normalized, dict):
                return True
            success_flag = bool(normalized.get("success", True))
            if success_flag:
                return True
            error_text = FastMCPStdioAdapter._extract_error_text_from_payload(normalized)
            if not error_text:
                return True
            lowered = error_text.lower()
            if "already set" in lowered or "already initialized" in lowered:
                return True
        return False

    def _tcp_reachable(self) -> Tuple[bool, Optional[str]]:
        parsed = urlparse(self.url)
        host = str(parsed.hostname or "").strip()
        if not host:
            return False, "missing_host"
        if parsed.port:
            port = int(parsed.port)
        elif str(parsed.scheme or "").strip().lower() == "https":
            port = 443
        else:
            port = 80
        timeout_sec = max(1.0, min(float(self.timeout), 3.0))
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                return True, None
        except Exception as exc:
            return False, f"{exc.__class__.__name__}"

    def is_available(self) -> bool:
        if self._availability_checked:
            return self._available
        if not self.url:
            self._available = False
            self._availability_reason = "missing_endpoint"
            self._availability_checked = True
            return False
        if not self.url.startswith(("http://", "https://")):
            self._available = False
            self._availability_reason = "invalid_endpoint"
            self._availability_checked = True
            return False
        health_url = self._health_url()
        health_timeout = max(1.0, min(float(self.timeout), 3.0))
        fallback_to_tcp_probe = False
        try:
            with httpx.Client(timeout=health_timeout, follow_redirects=True) as client:
                response = client.get(health_url, headers=self.headers)
            if response.status_code == 200:
                self._available = True
                self._availability_reason = None
                self._availability_checked = True
                return True
            if int(response.status_code) in {404, 405, 501}:
                fallback_to_tcp_probe = True
            else:
                self._available = False
                self._availability_reason = (
                    f"healthcheck_failed:status_{int(response.status_code)}@{health_url}"
                )
                self._availability_checked = True
                return False
        except Exception as exc:
            fallback_to_tcp_probe = isinstance(exc, httpx.RemoteProtocolError)
            if not fallback_to_tcp_probe:
                self._available = False
                self._availability_reason = (
                    f"healthcheck_failed:{exc.__class__.__name__}@{health_url}"
                )
                self._availability_checked = True
                return False

        if fallback_to_tcp_probe:
            reachable, tcp_reason = self._tcp_reachable()
            if reachable:
                self._available = True
                self._availability_reason = None
                self._availability_checked = True
                return True
            self._available = False
            self._availability_reason = (
                f"healthcheck_failed:tcp_unreachable:{tcp_reason or 'unknown'}@{health_url}"
            )
            self._availability_checked = True
            return False

        self._available = True
        self._availability_reason = None
        self._availability_checked = True
        return True

    @property
    def availability_reason(self) -> Optional[str]:
        if not self._availability_checked:
            self.is_available()
        return self._availability_reason

    def _build_http_mcp_client(self, *, candidate_url: str, transport: StreamableHttpTransport) -> MCPClient:
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
                client_context = self._build_http_mcp_client(
                    candidate_url=candidate_url,
                    transport=transport,
                )
                async with client_context as client:
                    list_tools = getattr(client, "list_tools", None)
                    if not callable(list_tools):
                        raise RuntimeError("mcp_list_tools_not_supported")
                    raw_tools = await list_tools()
                normalized = _normalize_tools_payload(raw_tools)
                if normalized:
                    return normalized
            except Exception as mcp_exc:
                if not self._is_transport_error_text(str(mcp_exc)):
                    raise
                last_exc = mcp_exc

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
                if normalized:
                    return normalized
                last_exc = RuntimeError("mcp_tools_list_empty")
            except Exception as bridge_exc:
                last_exc = bridge_exc
                continue

        if isinstance(last_exc, Exception):
            raise last_exc
        raise RuntimeError("mcp_http_list_tools_failed")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload_args = dict(arguments or {})
        candidate_urls = self._candidate_urls()
        if not candidate_urls:
            raise RuntimeError("missing_endpoint")

        request_headers = {"content-type": "application/json", **self.headers}
        last_exc: Optional[BaseException] = None

        for candidate_url in candidate_urls:
            # Preferred: use official FastMCP HTTP transport.
            try:
                transport = StreamableHttpTransport(
                    candidate_url,
                    headers=self.headers or None,
                )
                client_context = self._build_http_mcp_client(
                    candidate_url=candidate_url,
                    transport=transport,
                )
                async with client_context as client:
                    pre_bootstrap_needed = FastMCPStdioAdapter._should_bootstrap_for_tool(
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
                        should_bootstrap = FastMCPStdioAdapter._should_bootstrap_for_tool(
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
                data = FastMCPStdioAdapter._unwrap_tool_response(raw_result)
                needs_bootstrap = FastMCPStdioAdapter._should_bootstrap_for_tool(
                    tool_name,
                    FastMCPStdioAdapter._extract_error_text_from_payload(data),
                )
                if needs_bootstrap:
                    project_root = self._resolve_project_root_for_bootstrap(payload_args)
                    if project_root:
                        transport_retry = StreamableHttpTransport(
                            candidate_url,
                            headers=self.headers or None,
                        )
                        retry_context = self._build_http_mcp_client(
                            candidate_url=candidate_url,
                            transport=transport_retry,
                        )
                        async with retry_context as retry_client:
                            bootstrapped = await self._bootstrap_project_path(retry_client, project_root)
                            if bootstrapped:
                                retried = await retry_client.call_tool(tool_name, payload_args)
                                data = FastMCPStdioAdapter._unwrap_tool_response(retried)
                return self._normalize_tool_payload(data)
            except Exception as mcp_exc:
                if not self._is_transport_error_text(str(mcp_exc)):
                    raise
                last_exc = mcp_exc

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
        raise RuntimeError("mcp_http_call_failed")


@dataclass
class _AdapterSelection:
    adapter_key: str
    adapter_name: str
    adapter: MCPAdapter
    runtime_domain: str
    fallback_from: Optional[str] = None


class MCPRuntime:
    _VALID_RUNTIME_MODES = {
        "backend_only",
        "sandbox_only",
        "prefer_backend",
        "prefer_sandbox",
        "backend_then_sandbox",
        "sandbox_then_backend",
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
        prefer_mcp: bool = True,
        router: Optional[MCPToolRouter] = None,
        adapters: Optional[Dict[str, MCPAdapter]] = None,
        domain_adapters: Optional[Dict[str, Dict[str, MCPAdapter]]] = None,
        runtime_modes: Optional[Dict[str, str]] = None,
        required_mcps: Optional[List[str]] = None,
        write_scope_guard: Optional[TaskWriteScopeGuard] = None,
        adapter_failure_threshold: int = 2,
        default_runtime_mode: str = "backend_then_sandbox",
        strict_mode: bool = False,
        allow_filesystem_writes: bool = True,
        project_root: Optional[str] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.prefer_mcp = bool(prefer_mcp)
        self.strict_mode = bool(strict_mode)
        self.router = router or MCPToolRouter()
        self.adapters: Dict[str, MCPAdapter] = dict(adapters or {})
        self.domain_adapters: Dict[str, Dict[str, MCPAdapter]] = {}
        for mcp_name, domain_map in (domain_adapters or {}).items():
            normalized_name = str(mcp_name or "").strip()
            if not normalized_name:
                continue
            if not isinstance(domain_map, dict):
                continue
            normalized_domains: Dict[str, MCPAdapter] = {}
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
        self.required_mcps: List[str] = [
            str(name).strip()
            for name in (required_mcps or [])
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
        self._retrieval_cache_tools = {"qmd_query", "read_file", "search_code"}

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

    def _normalize_filesystem_arguments(self, route: MCPToolRoute) -> Dict[str, Any]:
        arguments = dict(route.arguments or {})
        if not self.project_root:
            return arguments
        normalized_tool = str(route.mcp_tool_name or "").strip().lower()
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

    def _normalize_code_index_arguments(self, route: MCPToolRoute) -> Dict[str, Any]:
        arguments = dict(route.arguments or {})
        if not self.project_root:
            return arguments
        arguments.setdefault("project_root", self.project_root)
        arguments.setdefault("project_path", self.project_root)
        normalized_tool = str(route.mcp_tool_name or "").strip().lower()
        if normalized_tool in {"search_code_advanced", "search_code", "find_files"}:
            arguments.setdefault("path", ".")
        return arguments

    def _prepare_route(self, route: MCPToolRoute) -> MCPToolRoute:
        adapter_name = str(route.adapter_name or "").strip().lower()
        if adapter_name == "filesystem":
            normalized_arguments = self._normalize_filesystem_arguments(route)
        elif adapter_name == "code_index":
            normalized_arguments = self._normalize_code_index_arguments(route)
        else:
            return route
        if normalized_arguments == route.arguments:
            return route
        return MCPToolRoute(
            adapter_name=route.adapter_name,
            mcp_tool_name=route.mcp_tool_name,
            arguments=normalized_arguments,
            is_write=route.is_write,
        )

    @classmethod
    def _normalize_runtime_mode(cls, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in cls._VALID_RUNTIME_MODES:
            return mode
        return "backend_then_sandbox"

    def _get_runtime_mode(self, mcp_name: str) -> str:
        normalized = str(mcp_name or "").strip()
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
        if mode_value in {"prefer_backend", "backend_then_sandbox"}:
            return ["backend", "sandbox"]
        if mode_value in {"prefer_sandbox", "sandbox_then_backend"}:
            return ["sandbox", "backend"]
        return ["backend", "sandbox"]

    @staticmethod
    def _adapter_runtime_domain(adapter: MCPAdapter) -> str:
        value = getattr(adapter, "runtime_domain", None)
        domain = str(value or "").strip().lower()
        return domain or "backend"

    @staticmethod
    def _adapter_available(adapter: MCPAdapter) -> Tuple[bool, Optional[str]]:
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
        normalized = str(adapter_name or "").strip().lower()
        return normalized != "local_proxy"

    @staticmethod
    def _failure_mode_for_adapter(adapter_name: str) -> Optional[str]:
        return None

    @staticmethod
    def _is_infra_error(error_text: str) -> bool:
        text = str(error_text or "").lower()
        if not text:
            return False
        infra_tokens = (
            "no such file or directory",
            "command not found",
            "enoent",
            "adapter unavailable",
            "missing_mcp_stdio_command",
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
        )
        return any(token in text for token in infra_tokens)

    @staticmethod
    def _is_expected_qmd_verify_error(
        *,
        mcp_name: str,
        agent_name: Optional[str],
        error_text: str,
    ) -> bool:
        if str(mcp_name or "").strip().lower() != "qmd":
            return False
        if str(agent_name or "").strip().lower() != "mcp_verify":
            return False
        lowered = str(error_text or "").strip().lower()
        if not lowered:
            return False
        expected_tokens = (
            "vector index not found",
            "run 'qmd embed'",
            "node-llama-cpp",
            "document not found",
            "collection not found",
            "no documents",
            "failed to parse jsonrpc",
            "compiler toolset",
            "failed to build llama.cpp",
        )
        return any(token in lowered for token in expected_tokens)

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

    def _resolve_adapter(self, route: MCPToolRoute) -> Tuple[Optional[_AdapterSelection], str]:
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

    def _required_mcp_names(self) -> List[str]:
        if self.required_mcps:
            return list(dict.fromkeys(self.required_mcps))
        inferred = list(self.adapters.keys()) + list(self.domain_adapters.keys())
        return list(dict.fromkeys(inferred))

    def _resolve_mcp_selection(self, mcp_name: str) -> Tuple[Optional[_AdapterSelection], str]:
        normalized_name = str(mcp_name or "").strip()
        if not normalized_name:
            return None, "adapter_unavailable"
        pseudo_route = MCPToolRoute(
            adapter_name=normalized_name,
            mcp_tool_name="tools/list",
            arguments={},
            is_write=False,
        )
        return self._resolve_adapter(pseudo_route)

    async def list_mcp_tools(self, mcp_name: str) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "success": False,
                "mcp_name": str(mcp_name or "").strip(),
                "tools": [],
                "error": "mcp_disabled",
                "metadata": {"mcp_used": False},
            }

        normalized_name = str(mcp_name or "").strip()
        selection, skip_reason = self._resolve_mcp_selection(normalized_name)
        if selection is None:
            return {
                "success": False,
                "mcp_name": normalized_name,
                "tools": [],
                "error": f"mcp_adapter_unavailable:{normalized_name or 'unknown'}",
                "metadata": {
                    "mcp_used": True,
                    "mcp_adapter": normalized_name or None,
                    "mcp_tool": "tools/list",
                    "mcp_skipped": True,
                    "mcp_skip_reason": skip_reason or "adapter_unavailable",
                },
            }

        try:
            tools = await selection.adapter.list_tools()
        except Exception as exc:
            error_text = f"{exc}"
            if self._is_infra_error(error_text):
                self._register_adapter_failure(selection.adapter_key)
            return {
                "success": False,
                "mcp_name": normalized_name,
                "tools": [],
                "error": f"mcp_list_tools_failed:{exc}",
                "metadata": {
                    "mcp_used": True,
                    "mcp_adapter": selection.adapter_name,
                    "mcp_tool": "tools/list",
                    "mcp_runtime_domain": selection.runtime_domain,
                    "mcp_runtime_fallback_used": bool(selection.fallback_from),
                    "mcp_runtime_fallback_from": selection.fallback_from,
                    "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                    "mcp_skipped": False,
                },
            }

        self._clear_adapter_failure(selection.adapter_key)
        return {
            "success": True,
            "mcp_name": normalized_name,
            "tools": _normalize_tools_payload(tools),
            "error": None,
            "metadata": {
                "mcp_used": True,
                "mcp_adapter": selection.adapter_name,
                "mcp_tool": "tools/list",
                "mcp_runtime_domain": selection.runtime_domain,
                "mcp_runtime_fallback_used": bool(selection.fallback_from),
                "mcp_runtime_fallback_from": selection.fallback_from,
                "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                "mcp_skipped": False,
            },
        }

    async def call_mcp_tool(
        self,
        *,
        mcp_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_name: Optional[str] = None,
        alias_used: Optional[str] = None,
    ) -> MCPExecutionResult:
        if not self.enabled:
            return MCPExecutionResult(handled=False, success=False)

        normalized_mcp = str(mcp_name or "").strip()
        normalized_tool = str(tool_name or "").strip()
        if not normalized_mcp or not normalized_tool:
            return MCPExecutionResult(
                handled=True,
                success=False,
                error="invalid_mcp_tool",
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": normalized_mcp or None,
                    "mcp_tool": normalized_tool or None,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_skipped": True,
                    "mcp_skip_reason": "invalid_mcp_tool",
                },
                should_fallback=False,
            )

        pseudo_route = MCPToolRoute(
            adapter_name=normalized_mcp,
            mcp_tool_name=normalized_tool,
            arguments=dict(arguments or {}),
            is_write=False,
        )
        selection, skip_reason = self._resolve_adapter(pseudo_route)
        if selection is None:
            mapped_reason = skip_reason or "adapter_unavailable"
            return MCPExecutionResult(
                handled=True,
                success=False,
                error=f"mcp_adapter_unavailable:{normalized_mcp}",
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": normalized_mcp,
                    "mcp_tool": normalized_tool,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_skipped": True,
                    "mcp_skip_reason": mapped_reason,
                },
                should_fallback=self._fallback_allowed_for_adapter(normalized_mcp),
            )

        try:
            payload = await selection.adapter.call_tool(normalized_tool, pseudo_route.arguments)
        except Exception as exc:
            error_text = f"{exc}"
            if self._is_expected_qmd_verify_error(
                mcp_name=normalized_mcp,
                agent_name=agent_name,
                error_text=error_text,
            ):
                logger.info(
                    "MCP direct tool call expected failure (%s/%s): %s",
                    normalized_mcp,
                    normalized_tool,
                    exc,
                )
            else:
                logger.warning(
                    "MCP direct tool call failed (%s/%s): %s",
                    normalized_mcp,
                    normalized_tool,
                    exc,
                )
            if self._is_infra_error(error_text):
                self._register_adapter_failure(selection.adapter_key)
            return MCPExecutionResult(
                handled=True,
                success=False,
                error=f"mcp_call_failed:{exc}",
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": selection.adapter_name,
                    "mcp_tool": normalized_tool,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_runtime_domain": selection.runtime_domain,
                    "mcp_runtime_fallback_used": bool(selection.fallback_from),
                    "mcp_runtime_fallback_from": selection.fallback_from,
                    "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                    "mcp_skipped": False,
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
            "mcp_used": True,
            "mcp_adapter": selection.adapter_name,
            "mcp_tool": normalized_tool,
            "agent": agent_name,
            "alias_used": alias_used,
            "mcp_runtime_domain": selection.runtime_domain,
            "mcp_runtime_fallback_used": bool(selection.fallback_from),
            "mcp_runtime_fallback_from": selection.fallback_from,
            "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
            "mcp_skipped": False,
        }
        if not success_flag and not error_text:
            error_text = "mcp_tool_failed"
        if not success_flag and self._is_infra_error(error_text or ""):
            self._register_adapter_failure(selection.adapter_key)
        if success_flag:
            self._clear_adapter_failure(selection.adapter_key)

        return MCPExecutionResult(
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
        normalized_tool = str(tool_name or "").strip().lower()
        route = self.router.route(tool_name, {})
        if not route:
            return False
        prepared_route = self._prepare_route(route)
        selection, _ = self._resolve_adapter(prepared_route)
        if selection is not None:
            return True

        fallback_route = self._build_search_code_route_fallback(
            tool_name=normalized_tool,
            route=prepared_route,
        )
        if fallback_route is None:
            return False
        fallback_route = self._prepare_route(fallback_route)
        fallback_selection, _ = self._resolve_adapter(fallback_route)
        return fallback_selection is not None

    def should_prefer_mcp(self) -> bool:
        return bool(self.enabled and self.prefer_mcp)

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

    def _ensure_local_proxy_adapter(self) -> LocalMCPProxyAdapter:
        existing = self.adapters.get("local_proxy")
        if isinstance(existing, LocalMCPProxyAdapter):
            return existing

        adapter = LocalMCPProxyAdapter(runtime_domain="backend")
        self.adapters["local_proxy"] = adapter
        return adapter

    def register_local_tool(self, tool_name: str, tool_obj: Any) -> bool:
        normalized = str(tool_name or "").strip()
        if not normalized:
            return False
        if tool_obj is None or not hasattr(tool_obj, "execute"):
            return False
        adapter = self._ensure_local_proxy_adapter()
        adapter.register_tool(normalized, tool_obj)
        if hasattr(self.router, "register_local_proxy_tool"):
            try:
                self.router.register_local_proxy_tool(normalized)
            except Exception:
                logger.debug("Failed to register local proxy route for %s", normalized)
        return True

    def register_local_tools(self, tools: Dict[str, Any]) -> int:
        count = 0
        for tool_name, tool_obj in (tools or {}).items():
            if self.register_local_tool(str(tool_name), tool_obj):
                count += 1
        return count

    @staticmethod
    def _normalize_fingerprint_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): MCPRuntime._normalize_fingerprint_value(value[key])
                for key in sorted(value.keys(), key=lambda item: str(item))
            }
        if isinstance(value, list):
            return [MCPRuntime._normalize_fingerprint_value(item) for item in value]
        return str(value)

    def _build_retrieval_cache_key(
        self,
        *,
        tool_name: str,
        route: MCPToolRoute,
    ) -> Optional[str]:
        normalized_tool = str(tool_name or "").strip().lower()
        if normalized_tool not in self._retrieval_cache_tools:
            return None
        payload = {
            "tool": normalized_tool,
            "adapter": str(route.adapter_name or "").strip().lower(),
            "mcp_tool": str(route.mcp_tool_name or "").strip().lower(),
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
    def _route_label(route: Optional[MCPToolRoute]) -> Optional[str]:
        if route is None:
            return None
        adapter_name = str(route.adapter_name or "").strip()
        mcp_tool_name = str(route.mcp_tool_name or "").strip()
        if adapter_name and mcp_tool_name:
            return f"{adapter_name}.{mcp_tool_name}"
        if adapter_name:
            return adapter_name
        if mcp_tool_name:
            return mcp_tool_name
        return None

    @staticmethod
    def _build_search_code_route_fallback(
        *,
        tool_name: str,
        route: MCPToolRoute,
    ) -> Optional[MCPToolRoute]:
        normalized_tool = str(tool_name or "").strip().lower()
        normalized_adapter = str(route.adapter_name or "").strip().lower()
        normalized_mcp_tool = str(route.mcp_tool_name or "").strip().lower()
        if normalized_tool != "search_code":
            return None
        if normalized_adapter != "code_index" or normalized_mcp_tool != "search_code_advanced":
            return None

        args = dict(route.arguments or {})
        pattern = str(
            args.get("pattern")
            or args.get("keyword")
            or args.get("query")
            or ""
        ).strip()
        fallback_args: Dict[str, Any] = {}
        if pattern:
            fallback_args["pattern"] = pattern
            fallback_args["query"] = pattern
            fallback_args["keyword"] = pattern

        path = str(args.get("path") or args.get("directory") or "").strip()
        if path:
            fallback_args["path"] = path
            fallback_args["directory"] = path

        glob = str(args.get("glob") or args.get("file_pattern") or "").strip()
        if glob:
            fallback_args["glob"] = glob
            fallback_args["file_pattern"] = glob

        for key in ("max_results", "case_sensitive", "is_regex"):
            if key in args:
                fallback_args[key] = args.get(key)

        return MCPToolRoute(
            adapter_name="filesystem",
            mcp_tool_name="search_files",
            arguments=fallback_args,
            is_write=False,
        )

    @staticmethod
    def _build_qmd_query_route_fallback(
        *,
        tool_name: str,
        route: MCPToolRoute,
    ) -> Optional[MCPToolRoute]:
        normalized_tool = str(tool_name or "").strip().lower()
        normalized_adapter = str(route.adapter_name or "").strip().lower()
        normalized_mcp_tool = str(route.mcp_tool_name or "").strip().lower()
        if normalized_tool != "qmd_query":
            return None
        if normalized_adapter != "qmd" or normalized_mcp_tool != "deep_search":
            return None

        fallback_args = dict(route.arguments or {})
        query_text = str(fallback_args.get("query") or "").strip()
        if not query_text:
            searches = fallback_args.get("searches")
            if isinstance(searches, list):
                parts: list[str] = []
                for item in searches:
                    if not isinstance(item, dict):
                        continue
                    segment = str(item.get("query") or "").strip()
                    if segment:
                        parts.append(segment)
                query_text = "\n".join(parts).strip()
        if query_text:
            fallback_args["query"] = query_text
        return MCPToolRoute(
            adapter_name="qmd",
            mcp_tool_name="query",
            arguments=fallback_args,
            is_write=False,
        )

    async def execute_tool(
        self,
        *,
        tool_name: str,
        tool_input: Dict[str, Any],
        agent_name: Optional[str] = None,
        alias_used: Optional[str] = None,
    ) -> MCPExecutionResult:
        if not self.enabled:
            return MCPExecutionResult(handled=False, success=False)

        normalized_tool_name = str(tool_name or "").strip().lower()
        route: Optional[MCPToolRoute] = self.router.route(tool_name, tool_input)
        if not route:
            return MCPExecutionResult(handled=False, success=False)
        route = self._prepare_route(route)
        primary_route = route
        fallback_route = self._build_search_code_route_fallback(
            tool_name=normalized_tool_name,
            route=primary_route,
        )
        if fallback_route is None:
            fallback_route = self._build_qmd_query_route_fallback(
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
            return MCPExecutionResult(
                handled=True,
                success=False,
                error=message,
                data=message,
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": route.adapter_name,
                    "mcp_tool": route.mcp_tool_name,
                    "mcp_route_primary": route_primary_label,
                    "mcp_route_fallback": route_fallback_label,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_skipped": True,
                    "mcp_skip_reason": "filesystem_readonly_policy",
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
                return MCPExecutionResult(
                    handled=True,
                    success=False,
                    error=message,
                    data=message,
                    metadata={
                        "mcp_used": True,
                        "mcp_adapter": route.adapter_name,
                        "mcp_tool": route.mcp_tool_name,
                        "mcp_route_primary": route_primary_label,
                        "mcp_route_fallback": route_fallback_label,
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
                    "mcp_runtime_cache_hit": True,
                    "mcp_runtime_cache_key": retrieval_cache_key,
                    "mcp_runtime_cache_stats": self.get_retrieval_cache_stats(),
                    "mcp_route_primary": route_primary_label,
                    "mcp_route_fallback": route_fallback_label,
                }
                return MCPExecutionResult(
                    handled=True,
                    success=bool(cached.get("success")),
                    data=str(cached.get("data") or ""),
                    error=str(cached.get("error") or "").strip() or None,
                    metadata=merged_cached_metadata,
                    should_fallback=False,
                )
            self._retrieval_cache_misses += 1

        attempt_plan: List[Tuple[str, MCPToolRoute]] = [("primary", primary_route)]
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
                return MCPExecutionResult(
                    handled=True,
                    success=False,
                    error=f"mcp_adapter_unavailable:{attempt_route.adapter_name}",
                    metadata={
                        "mcp_used": True,
                        "mcp_adapter": attempt_route.adapter_name,
                        "mcp_tool": attempt_route.mcp_tool_name,
                        "agent": agent_name,
                        "alias_used": alias_used,
                        "mcp_skipped": True,
                        "mcp_skip_reason": mapped_reason,
                        "mcp_failure_mode": failure_mode,
                        "mcp_runtime_cache_hit": False if retrieval_cache_key else None,
                        "mcp_runtime_fallback_used": bool(is_route_fallback),
                        "mcp_runtime_fallback_from": route_primary_label if is_route_fallback else None,
                        "mcp_runtime_fallback_to": None,
                        "mcp_route_primary": route_primary_label,
                        "mcp_route_fallback": route_fallback_label,
                        **self._metadata_from_write_scope(decision=write_decision),
                    },
                    should_fallback=self._fallback_allowed_for_adapter(attempt_route.adapter_name),
                )

            try:
                payload = await selection.adapter.call_tool(
                    attempt_route.mcp_tool_name,
                    attempt_route.arguments,
                )
            except Exception as exc:
                logger.warning(
                    "MCP tool call failed (%s/%s): %s",
                    attempt_route.adapter_name,
                    attempt_route.mcp_tool_name,
                    exc,
                )
                error_text = f"{exc}"
                if self._is_infra_error(error_text):
                    self._register_adapter_failure(selection.adapter_key)
                if attempt_index < len(attempt_plan) - 1:
                    continue
                failure_mode = self._failure_mode_for_adapter(selection.adapter_name)
                runtime_fallback_used = bool(selection.fallback_from) or bool(is_route_fallback)
                return MCPExecutionResult(
                    handled=True,
                    success=False,
                    error=f"mcp_call_failed:{exc}",
                    metadata={
                        "mcp_used": True,
                        "mcp_adapter": selection.adapter_name,
                        "mcp_tool": attempt_route.mcp_tool_name,
                        "agent": agent_name,
                        "alias_used": alias_used,
                        "mcp_runtime_domain": selection.runtime_domain,
                        "mcp_runtime_fallback_used": runtime_fallback_used,
                        "mcp_runtime_fallback_from": (
                            selection.fallback_from
                            if selection.fallback_from
                            else (route_primary_label if is_route_fallback else None)
                        ),
                        "mcp_runtime_fallback_to": (
                            selection.runtime_domain if runtime_fallback_used else None
                        ),
                        "mcp_route_primary": route_primary_label,
                        "mcp_route_fallback": route_fallback_label,
                        "mcp_skipped": False,
                        "mcp_failure_mode": failure_mode,
                        "mcp_runtime_cache_hit": False if retrieval_cache_key else None,
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
                "mcp_used": True,
                "mcp_adapter": selection.adapter_name,
                "mcp_tool": attempt_route.mcp_tool_name,
                "agent": agent_name,
                "alias_used": alias_used,
                "mcp_runtime_domain": selection.runtime_domain,
                "mcp_runtime_fallback_used": runtime_fallback_used,
                "mcp_runtime_fallback_from": (
                    selection.fallback_from
                    if selection.fallback_from
                    else (route_primary_label if is_route_fallback else None)
                ),
                "mcp_runtime_fallback_to": (
                    selection.runtime_domain if runtime_fallback_used else None
                ),
                "mcp_route_primary": route_primary_label,
                "mcp_route_fallback": route_fallback_label,
                "mcp_skipped": False,
                "mcp_failure_mode": self._failure_mode_for_adapter(selection.adapter_name),
                "mcp_runtime_cache_hit": False if retrieval_cache_key else None,
                **self._metadata_from_write_scope(decision=write_decision),
            }

            if not success_flag and not error_text:
                error_text = "mcp_tool_failed"
            if not success_flag and self._is_infra_error(error_text or ""):
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
                        "mcp_runtime_cache_key": retrieval_cache_key,
                        "mcp_runtime_cache_stats": self.get_retrieval_cache_stats(),
                    }
                return MCPExecutionResult(
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
                    "mcp_runtime_cache_key": retrieval_cache_key,
                    "mcp_runtime_cache_stats": self.get_retrieval_cache_stats(),
                }

            return MCPExecutionResult(
                handled=True,
                success=False,
                data=output_text,
                error=error_text,
                metadata=merged_metadata,
                should_fallback=self._fallback_allowed_for_adapter(selection.adapter_name),
            )

        return MCPExecutionResult(handled=False, success=False)

    def ensure_all_mcp_ready(self, runtime_domain: str = "backend") -> Dict[str, Any]:
        domain_value = str(runtime_domain or "backend").strip().lower() or "backend"
        required = self._required_mcp_names()

        details: Dict[str, Dict[str, Any]] = {}
        not_ready: List[Dict[str, str]] = []

        for mcp_name in required:
            mcp_details: Dict[str, Any] = {"required": True, "runtime_mode": self._get_runtime_mode(mcp_name)}
            if domain_value == "all":
                domains = self._candidate_domains_for_mode(self._get_runtime_mode(mcp_name))
                if not domains:
                    domains = ["backend"]
            else:
                domains = [domain_value]
            normalized_domains: List[str] = []
            for domain in domains:
                domain_key = str(domain or "").strip().lower()
                if domain_key and domain_key not in normalized_domains:
                    normalized_domains.append(domain_key)
            for domain in normalized_domains:
                ready, reason = self._check_mcp_ready_for_domain(mcp_name, domain)
                mcp_details[domain] = {"ready": ready, "reason": reason}
                if not ready:
                    not_ready.append(
                        {
                            "mcp": mcp_name,
                            "runtime_domain": domain,
                            "reason": reason,
                        }
                    )
            details[mcp_name] = mcp_details

        return {
            "ready": len(not_ready) == 0,
            "runtime_domain": domain_value,
            "required_mcps": required,
            "not_ready": not_ready,
            "details": details,
        }

    def _check_mcp_ready_for_domain(self, mcp_name: str, runtime_domain: str) -> Tuple[bool, str]:
        mcp_key = str(mcp_name or "").strip()
        domain = str(runtime_domain or "").strip().lower()
        if not mcp_key or not domain:
            return False, "invalid_runtime_domain"

        domain_map = self.domain_adapters.get(mcp_key)
        if domain_map is not None:
            adapter = domain_map.get(domain)
            if adapter is None:
                return False, "domain_adapter_missing"
            adapter_key = f"{mcp_key}:{domain}"
            if self._is_adapter_disabled(adapter_key):
                return False, "adapter_disabled_after_failures"
            available, reason = self._adapter_available(adapter)
            if not available:
                return False, reason or "adapter_unavailable"
            return True, "ready"

        adapter = self.adapters.get(mcp_key)
        if adapter is None:
            return False, "adapter_unavailable"
        adapter_domain = self._adapter_runtime_domain(adapter)
        if adapter_domain != domain:
            return False, "adapter_domain_mismatch"
        adapter_key = mcp_key if domain == "backend" else f"{mcp_key}:{domain}"
        if self._is_adapter_disabled(adapter_key):
            return False, "adapter_disabled_after_failures"
        available, reason = self._adapter_available(adapter)
        if not available:
            return False, reason or "adapter_unavailable"
        return True, "ready"
