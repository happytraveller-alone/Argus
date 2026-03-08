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
    """Route public scan-core tool names to stdio MCP tools."""

    def __init__(self) -> None:
        self._route_map = {
            "read_file": ("filesystem", "read_file", False),
            "list_files": ("code_index", "find_files", False),
            "search_code": ("code_index", "search_code_advanced", False),
            "extract_function": ("code_index", "get_symbol_body", False),
            "locate_enclosing_function": ("code_index", "get_file_summary", False),
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
            query = (
                _non_empty_string(payload.get("query"))
                or _non_empty_string(payload.get("keyword"))
                or _non_empty_string(payload.get("pattern"))
            )
            if query:
                payload["query"] = query
                if is_regex:
                    payload["pattern"] = query
                else:
                    payload.pop("pattern", None)
            payload["regex"] = is_regex
            path_value = _sanitize_path(payload.get("path") or payload.get("file_path"))
            if path_value:
                payload["path"] = path_value
            glob_value = _non_empty_string(payload.get("glob") or payload.get("file_pattern"))
            if glob_value:
                payload["glob"] = glob_value

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
            payload.pop("function_name", None)

        elif tool_name == "locate_enclosing_function":
            path_value = _sanitize_path(payload.get("file_path") or payload.get("path"))
            if path_value:
                payload["path"] = path_value
            raw_line = payload.get("line") if payload.get("line") is not None else payload.get("line_start")
            if raw_line is not None:
                try:
                    payload["line"] = max(1, int(raw_line))
                except Exception:
                    pass
            payload.setdefault("include_symbols", True)

        return payload

    def can_route(self, tool_name: str) -> bool:
        return self._normalize_tool_name(tool_name) in self._route_map

    def is_write_tool(self, tool_name: str) -> bool:
        return False

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
