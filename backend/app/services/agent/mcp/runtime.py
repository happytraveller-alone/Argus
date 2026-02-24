from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from fastmcp import Client as MCPClient
from fastmcp.client.transports import StdioTransport

from .router import MCPToolRoute, MCPToolRouter
from .write_scope import TaskWriteScopeGuard, WriteScopeDecision

logger = logging.getLogger(__name__)


class MCPAdapter(Protocol):
    runtime_domain: str

    def is_available(self) -> bool:
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

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        transport = self._build_transport()
        async with MCPClient(transport=transport, timeout=self.timeout) as client:
            raw_result = await client.call_tool(tool_name, arguments)
        payload = self._unwrap_tool_response(raw_result)
        if not isinstance(payload, dict):
            return {"success": False, "error": "mcp_invalid_payload"}
        return payload


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
    ) -> None:
        self.enabled = bool(enabled)
        self.prefer_mcp = bool(prefer_mcp)
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
        self._adapter_failure_counts: Dict[str, int] = {}
        self._adapter_disabled: Dict[str, bool] = {}

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
        )
        return any(token in text for token in infra_tokens)

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
            for domain in domains:
                adapter = domain_map.get(domain)
                if adapter is None:
                    continue
                adapter_key = f"{adapter_name}:{domain}"
                if self._is_adapter_disabled(adapter_key):
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

    def can_handle(self, tool_name: str) -> bool:
        if not self.enabled:
            return False
        route = self.router.route(tool_name, {})
        if not route:
            return False
        selection, _ = self._resolve_adapter(route)
        return selection is not None

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

        route: Optional[MCPToolRoute] = self.router.route(tool_name, tool_input)
        if not route:
            return MCPExecutionResult(handled=False, success=False)

        write_decision: Optional[WriteScopeDecision] = None
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
                        "agent": agent_name,
                        "alias_used": alias_used,
                        **self._metadata_from_write_scope(decision=write_decision),
                    },
                    should_fallback=False,
                )

        selection, skip_reason = self._resolve_adapter(route)
        if selection is None:
            mapped_reason = skip_reason or "adapter_unavailable"
            return MCPExecutionResult(
                handled=True,
                success=False,
                error=f"mcp_adapter_unavailable:{route.adapter_name}",
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": route.adapter_name,
                    "mcp_tool": route.mcp_tool_name,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_skipped": True,
                    "mcp_skip_reason": mapped_reason,
                    **self._metadata_from_write_scope(decision=write_decision),
                },
                should_fallback=True,
            )

        try:
            payload = await selection.adapter.call_tool(route.mcp_tool_name, route.arguments)
        except Exception as exc:
            logger.warning("MCP tool call failed (%s/%s): %s", route.adapter_name, route.mcp_tool_name, exc)
            error_text = f"{exc}"
            if self._is_infra_error(error_text):
                self._register_adapter_failure(selection.adapter_key)
            return MCPExecutionResult(
                handled=True,
                success=False,
                error=f"mcp_call_failed:{exc}",
                metadata={
                    "mcp_used": True,
                    "mcp_adapter": selection.adapter_name,
                    "mcp_tool": route.mcp_tool_name,
                    "agent": agent_name,
                    "alias_used": alias_used,
                    "mcp_runtime_domain": selection.runtime_domain,
                    "mcp_runtime_fallback_used": bool(selection.fallback_from),
                    "mcp_runtime_fallback_from": selection.fallback_from,
                    "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
                    "mcp_skipped": False,
                    **self._metadata_from_write_scope(decision=write_decision),
                },
                should_fallback=True,
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
            "mcp_tool": route.mcp_tool_name,
            "agent": agent_name,
            "alias_used": alias_used,
            "mcp_runtime_domain": selection.runtime_domain,
            "mcp_runtime_fallback_used": bool(selection.fallback_from),
            "mcp_runtime_fallback_from": selection.fallback_from,
            "mcp_runtime_fallback_to": selection.runtime_domain if selection.fallback_from else None,
            "mcp_skipped": False,
            **self._metadata_from_write_scope(decision=write_decision),
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
            should_fallback=not success_flag,
        )

    def ensure_all_mcp_ready(self, runtime_domain: str = "backend") -> Dict[str, Any]:
        domain_value = str(runtime_domain or "backend").strip().lower() or "backend"
        domains = ["backend", "sandbox"] if domain_value == "all" else [domain_value]
        required = self._required_mcp_names()

        details: Dict[str, Dict[str, Any]] = {}
        not_ready: List[Dict[str, str]] = []

        for mcp_name in required:
            mcp_details: Dict[str, Any] = {"required": True, "runtime_mode": self._get_runtime_mode(mcp_name)}
            for domain in domains:
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
