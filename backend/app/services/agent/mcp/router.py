from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MCPToolRoute:
    adapter_name: str
    mcp_tool_name: str
    arguments: Dict[str, Any]
    is_write: bool = False


class MCPToolRouter:
    """Route public scan-core tool names to local tools or MCP tools."""

    _LOCAL_ROUTE_ADAPTER = "__local__"

    def __init__(self) -> None:
        self._route_map = {
            "read_file": (self._LOCAL_ROUTE_ADAPTER, "read_file", False),
            "list_files": (self._LOCAL_ROUTE_ADAPTER, "list_files", False),
            "search_code": (self._LOCAL_ROUTE_ADAPTER, "search_code", False),
            "extract_function": (self._LOCAL_ROUTE_ADAPTER, "extract_function", False),
            "locate_enclosing_function": (
                self._LOCAL_ROUTE_ADAPTER,
                "locate_enclosing_function",
                False,
            ),
            # Local-registered routes: these tools are valid Agent tools but are currently
            # executed via local tool implementations (strict-mode fallback allowlist).
            "think": (self._LOCAL_ROUTE_ADAPTER, "think", False),
            "reflect": (self._LOCAL_ROUTE_ADAPTER, "reflect", False),
            "smart_scan": (self._LOCAL_ROUTE_ADAPTER, "smart_scan", False),
            "quick_audit": (self._LOCAL_ROUTE_ADAPTER, "quick_audit", False),
            "pattern_match": (self._LOCAL_ROUTE_ADAPTER, "pattern_match", False),
            "dataflow_analysis": (self._LOCAL_ROUTE_ADAPTER, "dataflow_analysis", False),
            "controlflow_analysis_light": (
                self._LOCAL_ROUTE_ADAPTER,
                "controlflow_analysis_light",
                False,
            ),
            "logic_authz_analysis": (self._LOCAL_ROUTE_ADAPTER, "logic_authz_analysis", False),
            "sandbox_exec": (self._LOCAL_ROUTE_ADAPTER, "sandbox_exec", False),
            "verify_vulnerability": (self._LOCAL_ROUTE_ADAPTER, "verify_vulnerability", False),
            "run_code": (self._LOCAL_ROUTE_ADAPTER, "run_code", False),
            "create_vulnerability_report": (
                self._LOCAL_ROUTE_ADAPTER,
                "create_vulnerability_report",
                False,
            ),
            "save_verification_result": (
                self._LOCAL_ROUTE_ADAPTER,
                "save_verification_result",
                False,
            ),
            "push_finding_to_queue": (self._LOCAL_ROUTE_ADAPTER, "push_finding_to_queue", True),
            "is_finding_in_queue": (self._LOCAL_ROUTE_ADAPTER, "is_finding_in_queue", False),
            "get_queue_status": (self._LOCAL_ROUTE_ADAPTER, "get_queue_status", False),
            "dequeue_finding": (self._LOCAL_ROUTE_ADAPTER, "dequeue_finding", True),
            "push_risk_point_to_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "push_risk_point_to_queue",
                True,
            ),
            "push_risk_points_to_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "push_risk_points_to_queue",
                True,
            ),
            "get_recon_risk_queue_status": (
                self._LOCAL_ROUTE_ADAPTER,
                "get_recon_risk_queue_status",
                False,
            ),
            "dequeue_recon_risk_point": (
                self._LOCAL_ROUTE_ADAPTER,
                "dequeue_recon_risk_point",
                True,
            ),
            "peek_recon_risk_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "peek_recon_risk_queue",
                False,
            ),
            "clear_recon_risk_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "clear_recon_risk_queue",
                True,
            ),
            "is_recon_risk_point_in_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "is_recon_risk_point_in_queue",
                False,
            ),
            "push_bl_risk_point_to_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "push_bl_risk_point_to_queue",
                True,
            ),
            "push_bl_risk_points_to_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "push_bl_risk_points_to_queue",
                True,
            ),
            "get_bl_risk_queue_status": (
                self._LOCAL_ROUTE_ADAPTER,
                "get_bl_risk_queue_status",
                False,
            ),
            "dequeue_bl_risk_point": (
                self._LOCAL_ROUTE_ADAPTER,
                "dequeue_bl_risk_point",
                True,
            ),
            "peek_bl_risk_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "peek_bl_risk_queue",
                False,
            ),
            "clear_bl_risk_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "clear_bl_risk_queue",
                True,
            ),
            "is_bl_risk_point_in_queue": (
                self._LOCAL_ROUTE_ADAPTER,
                "is_bl_risk_point_in_queue",
                False,
            ),
        }

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        return str(tool_name or "").strip().lower()

    _FUNCTION_NAME_PATTERNS = (
        re.compile(r"\bdef\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        re.compile(r"\bfunction\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
        re.compile(r"\b(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
        re.compile(r"(?:^|\n)\s*(?:[A-Za-z_~][A-Za-z0-9_:<>\[\]\s*&]*\s+)+(?P<name>[A-Za-z_~][A-Za-z0-9_:]*)\s*\([^;{}]*\)\s*\{"),
    )
    _FUNCTION_NAME_STOPWORDS = {"if", "for", "while", "switch", "catch", "return"}

    @classmethod
    def _infer_function_name_from_code(cls, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        code = value.strip()
        if not code:
            return None
        for pattern in cls._FUNCTION_NAME_PATTERNS:
            match = pattern.search(code)
            if not match:
                continue
            candidate = str(match.group("name") or "").strip()
            if not candidate:
                continue
            base_name = candidate.split("::")[-1]
            if base_name.lower() in cls._FUNCTION_NAME_STOPWORDS:
                continue
            return candidate
        return None

    @staticmethod
    def _normalize_search_scope_directory(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        normalized = value.strip().replace("\\", "/").strip("`'\"")
        if not normalized:
            return None
        while normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = normalized.rstrip("/")
        if normalized in {"", "."}:
            return None
        return normalized

    @staticmethod
    def _split_path_and_line(value: Any) -> tuple[Optional[str], Optional[int]]:
        if not isinstance(value, str):
            return None, None
        normalized = value.strip().replace("\\", "/").strip("`'\"")
        if not normalized:
            return None, None
        match = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", normalized)
        if not match:
            return normalized, None
        path_part = str(match.group(1) or "").strip()
        if not path_part:
            return normalized, None
        try:
            line_start = max(1, int(match.group(2)))
        except Exception:
            line_start = None
        return path_part, line_start

    @classmethod
    def _merge_search_file_pattern(
        cls,
        directory: Optional[str],
        file_pattern: Optional[str],
    ) -> Optional[str]:
        normalized_directory = cls._normalize_search_scope_directory(directory)
        normalized_pattern = file_pattern.strip() if isinstance(file_pattern, str) else ""
        normalized_pattern = normalized_pattern.replace("\\", "/").strip("`'\"")
        while normalized_pattern.startswith("./"):
            normalized_pattern = normalized_pattern[2:]

        if not normalized_directory:
            return normalized_pattern or None

        directory_prefix = f"{normalized_directory}/**"
        if not normalized_pattern:
            return directory_prefix
        if normalized_pattern.startswith(f"{normalized_directory}/"):
            return normalized_pattern
        return f"{directory_prefix}/{normalized_pattern}"

    @staticmethod
    def _normalize_arguments(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(tool_input or {})

        def _non_empty_string(value: Any) -> Optional[str]:
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    return normalized
            return None

        def _sanitize_path(value: Any) -> Optional[str]:
            normalized = _non_empty_string(value)
            if not normalized:
                return None
            return normalized.replace("\\", "/").strip("`'\"")

        if tool_name == "list_files":
            path_value = _sanitize_path(payload.get("path") or payload.get("directory"))
            if path_value:
                payload["path"] = path_value
            pattern = (
                _non_empty_string(payload.get("pattern"))
                or _non_empty_string(payload.get("file_pattern"))
                or _non_empty_string(payload.get("glob"))
                or "*"
            )
            payload["pattern"] = pattern

        elif tool_name == "search_code":
            explicit_regex = payload.get("is_regex")
            if explicit_regex is None:
                explicit_regex = payload.get("regex")
            is_regex = bool(explicit_regex)
            pattern = (
                _non_empty_string(payload.get("pattern"))
                or _non_empty_string(payload.get("query"))
                or _non_empty_string(payload.get("keyword"))
            )

            path_value = _sanitize_path(payload.get("path") or payload.get("file_path"))
            normalized_file_pattern = MCPToolRouter._merge_search_file_pattern(
                payload.get("directory"),
                _non_empty_string(payload.get("file_pattern")) or _non_empty_string(payload.get("glob")),
            )

            normalized_payload: Dict[str, Any] = {"regex": is_regex}
            if pattern:
                normalized_payload["pattern"] = pattern
            if path_value:
                normalized_payload["path"] = path_value
            elif payload.get("directory") is not None:
                normalized_payload["path"] = _sanitize_path(payload.get("directory")) or "."
            if normalized_file_pattern:
                normalized_payload["file_pattern"] = normalized_file_pattern
            for key in ("case_sensitive", "context_lines", "fuzzy", "start_index", "max_results"):
                if payload.get(key) is not None:
                    normalized_payload[key] = payload.get(key)
            payload = normalized_payload

        elif tool_name == "read_file":
            path_value = _sanitize_path(payload.get("file_path") or payload.get("path"))
            if path_value:
                payload["path"] = path_value

        elif tool_name == "extract_function":
            path_value = _sanitize_path(
                payload.get("file_path") or payload.get("path") or payload.get("file_name")
            )
            if path_value:
                payload["path"] = path_value
            symbol = (
                _non_empty_string(payload.get("symbol_name"))
                or _non_empty_string(payload.get("symbol"))
                or _non_empty_string(payload.get("function_name"))
                or MCPToolRouter._infer_function_name_from_code(payload.get("code"))
            )
            if symbol:
                payload["symbol_name"] = symbol
                payload["symbol"] = symbol
            raw_line = payload.get("line") if payload.get("line") is not None else payload.get("line_start")
            if raw_line is not None:
                try:
                    normalized_line = max(1, int(raw_line))
                except Exception:
                    normalized_line = None
                if normalized_line is not None:
                    payload["line"] = normalized_line
                    payload["line_start"] = normalized_line
            payload.pop("code", None)
            payload.pop("file_name", None)
            payload.pop("file_path", None)
            payload.pop("function_name", None)

        elif tool_name == "locate_enclosing_function":
            raw_path_value = _sanitize_path(payload.get("file_path") or payload.get("path"))
            parsed_path, parsed_line = MCPToolRouter._split_path_and_line(raw_path_value)
            if parsed_path:
                payload["path"] = parsed_path
            raw_line = (
                payload.get("line_start")
                if payload.get("line_start") is not None
                else payload.get("line")
            )
            if raw_line is None:
                raw_line = parsed_line
            if raw_line is not None:
                try:
                    normalized_line = max(1, int(raw_line))
                    payload["line"] = normalized_line
                    payload["line_start"] = normalized_line
                except Exception:
                    pass
            payload.setdefault("include_symbols", True)

        return payload

    def can_route(self, tool_name: str) -> bool:
        return self._normalize_tool_name(tool_name) in self._route_map

    def is_write_tool(self, tool_name: str) -> bool:
        normalized_name = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized_name)
        if route is None:
            return False
        return bool(route[2])

    def is_local_only_tool(self, tool_name: str) -> bool:
        normalized_name = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized_name)
        if route is None:
            return False
        adapter_name, _, _ = route
        return str(adapter_name or "").strip().lower() == self._LOCAL_ROUTE_ADAPTER

    def route(self, tool_name: str, tool_input: Optional[Dict[str, Any]] = None) -> Optional[MCPToolRoute]:
        normalized_name = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized_name)
        if route is None:
            return None
        adapter_name, mcp_tool_name, is_write = route
        normalized_arguments = self._normalize_arguments(normalized_name, tool_input or {})
        return MCPToolRoute(
            adapter_name=adapter_name,
            mcp_tool_name=mcp_tool_name,
            arguments=normalized_arguments,
            is_write=bool(is_write),
        )
