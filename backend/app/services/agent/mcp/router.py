from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, Optional, Set


@dataclass(frozen=True)
class MCPToolRoute:
    adapter_name: str
    mcp_tool_name: str
    arguments: Dict[str, Any]
    is_write: bool = False


class MCPToolRouter:
    """Route local skill/tool names to MCP server tools.

    This layer intentionally keeps the mapping explicit and narrow.
    """

    def __init__(self) -> None:
        self._blocked_virtual_names = {
            "code_search",
            "rag_query",
            "security_search",
            "query_security_knowledge",
            "get_vulnerability_knowledge",
            "function_context",
        }
        self._route_map = {
            "read_file": ("filesystem", "read_file", False),
            "list_files": ("code_index", "find_files", False),
            "search_code": ("code_index", "search_code_advanced", False),
            "extract_function": ("code_index", "get_symbol_body", False),
            "locate_enclosing_function": ("code_index", "get_file_summary", False),
            "qmd_query": ("qmd", "deep_search", False),
            "qmd_get": ("qmd", "get", False),
            "qmd_multi_get": ("qmd", "multi_get", False),
            "qmd_status": ("qmd", "status", False),
            "sequential_thinking": ("sequentialthinking", "sequentialthinking", False),
            "reasoning_trace": ("sequentialthinking", "sequentialthinking", False),
            "sequentialthinking": ("sequentialthinking", "sequentialthinking", False),
            "edit_file": ("filesystem", "edit_file", True),
            "write_file": ("filesystem", "write_file", True),
        }
        self._local_proxy_tools: Set[str] = set()

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        return str(tool_name or "").strip().lower()

    _FUNCTION_NAME_PATTERNS = (
        re.compile(r"\bdef\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        re.compile(r"\bfunction\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
        re.compile(
            r"\b(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
        ),
        re.compile(
            r"(?:^|\n)\s*(?:[A-Za-z_~][A-Za-z0-9_:<>\[\]\s*&]*\s+)+(?P<name>[A-Za-z_~][A-Za-z0-9_:]*)\s*\([^;{}]*\)\s*\{"
        ),
    )
    _FUNCTION_NAME_STOPWORDS = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
    }

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
            return base_name
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

        if tool_name == "list_files":
            directory = _non_empty_string(payload.get("directory"))
            if directory and "path" not in payload:
                payload["path"] = directory
            pattern = (
                _non_empty_string(payload.get("pattern"))
                or _non_empty_string(payload.get("file_pattern"))
                or _non_empty_string(payload.get("glob"))
            )
            if not pattern:
                pattern = "*"
            payload["pattern"] = pattern

        if tool_name == "search_code":
            normalized_pattern = (
                _non_empty_string(payload.get("pattern"))
                or _non_empty_string(payload.get("keyword"))
                or _non_empty_string(payload.get("query"))
            )
            if normalized_pattern and "pattern" not in payload:
                payload["pattern"] = normalized_pattern

            keyword = _non_empty_string(payload.get("keyword"))
            if keyword and "query" not in payload:
                payload["query"] = keyword
            elif normalized_pattern and "query" not in payload:
                payload["query"] = normalized_pattern

            directory = _non_empty_string(payload.get("directory"))
            if directory and "path" not in payload:
                payload["path"] = directory

            file_pattern = _non_empty_string(payload.get("file_pattern"))
            if file_pattern and "glob" not in payload:
                payload["glob"] = file_pattern

        if tool_name == "read_file":
            file_path = payload.get("file_path") or payload.get("path")
            if isinstance(file_path, str) and file_path.strip():
                payload["path"] = file_path.strip()

        if tool_name in {"edit_file", "write_file"}:
            file_path = payload.get("file_path") or payload.get("path")
            if isinstance(file_path, str) and file_path.strip():
                payload["path"] = file_path.strip()

        if tool_name == "extract_function":
            normalized_path = (
                _non_empty_string(payload.get("file_path"))
                or _non_empty_string(payload.get("path"))
                or _non_empty_string(payload.get("file_name"))
            )
            if normalized_path:
                payload["path"] = normalized_path

            normalized_symbol = (
                _non_empty_string(payload.get("symbol_name"))
                or _non_empty_string(payload.get("symbol"))
                or _non_empty_string(payload.get("function_name"))
                or MCPToolRouter._infer_function_name_from_code(payload.get("code"))
            )
            if normalized_symbol:
                payload["symbol_name"] = normalized_symbol
                payload["symbol"] = normalized_symbol

            raw_line = payload.get("line")
            if raw_line is None:
                raw_line = payload.get("line_start")
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

        if tool_name == "locate_enclosing_function":
            file_path = payload.get("file_path") or payload.get("path")
            if isinstance(file_path, str) and file_path.strip():
                payload["path"] = file_path.strip()
            line_start = payload.get("line_start") or payload.get("line")
            if line_start is not None and "line" not in payload:
                payload["line"] = line_start
            payload.setdefault("include_symbols", True)

        if tool_name == "qmd_query":
            query = payload.get("query")
            if "searches" not in payload and isinstance(query, str) and query.strip():
                payload["searches"] = [{"type": "vec", "query": query.strip()}]
            if "query" not in payload and isinstance(payload.get("searches"), list):
                synthetic_query = MCPToolRouter._build_qmd_query_text(payload.get("searches"))
                if synthetic_query:
                    payload["query"] = synthetic_query
            if "collections" in payload and isinstance(payload.get("collections"), str):
                raw = str(payload["collections"]).strip()
                payload["collections"] = [raw] if raw else []

        if tool_name == "qmd_get":
            doc_id = payload.get("doc_id") or payload.get("id")
            if isinstance(doc_id, str) and doc_id.strip():
                payload["id"] = doc_id.strip()

        if tool_name == "qmd_multi_get":
            ids = payload.get("ids") or payload.get("doc_ids")
            if isinstance(ids, str):
                split_ids = [part.strip() for part in ids.replace(";", ",").split(",")]
                payload["ids"] = [part for part in split_ids if part]
            elif isinstance(ids, list):
                payload["ids"] = [str(item).strip() for item in ids if str(item).strip()]

        if tool_name in {"sequential_thinking", "reasoning_trace", "sequentialthinking"}:
            thought = (
                _non_empty_string(payload.get("thought"))
                or _non_empty_string(payload.get("goal"))
                or _non_empty_string(payload.get("query"))
                or "startup_probe"
            )
            payload["thought"] = thought
            if "nextThoughtNeeded" not in payload:
                payload["nextThoughtNeeded"] = bool(payload.get("needsMoreThoughts", False))
            if "thoughtNumber" not in payload:
                raw_number = payload.get("thought_number", payload.get("step_index", 1))
                try:
                    payload["thoughtNumber"] = max(1, int(raw_number))
                except Exception:
                    payload["thoughtNumber"] = 1
            if "totalThoughts" not in payload:
                raw_total = payload.get("total_steps", payload.get("max_steps", payload.get("thoughtNumber", 1)))
                try:
                    payload["totalThoughts"] = max(int(payload.get("thoughtNumber", 1)), int(raw_total))
                except Exception:
                    payload["totalThoughts"] = max(1, int(payload.get("thoughtNumber", 1)))

        return payload

    @staticmethod
    def _build_qmd_query_text(searches: Any) -> str:
        if not isinstance(searches, list):
            return ""
        lines: list[str] = []
        for item in searches:
            if not isinstance(item, dict):
                continue
            query_text = str(item.get("query") or "").strip()
            if not query_text:
                continue
            query_type = str(item.get("type") or "").strip().lower() or "vec"
            lines.append(f"{query_type}: {query_text}")
        return "\n".join(lines)

    def can_route(self, tool_name: str) -> bool:
        normalized = self._normalize_tool_name(tool_name)
        return normalized in self._route_map or normalized in self._local_proxy_tools

    def is_write_tool(self, tool_name: str) -> bool:
        normalized = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized)
        return bool(route and route[2])

    def register_local_proxy_tool(self, tool_name: str) -> bool:
        normalized = self._normalize_tool_name(tool_name)
        if not normalized:
            return False
        if normalized in self._blocked_virtual_names:
            return False
        if normalized in self._route_map:
            return False
        before = len(self._local_proxy_tools)
        self._local_proxy_tools.add(normalized)
        return len(self._local_proxy_tools) > before

    def register_local_proxy_tools(self, tool_names: Iterable[str]) -> int:
        added = 0
        for name in tool_names:
            if self.register_local_proxy_tool(str(name)):
                added += 1
        return added

    def is_local_proxy_tool(self, tool_name: str) -> bool:
        return self._normalize_tool_name(tool_name) in self._local_proxy_tools

    def route(self, tool_name: str, tool_input: Dict[str, Any]) -> Optional[MCPToolRoute]:
        normalized_tool_name = self._normalize_tool_name(tool_name)
        if normalized_tool_name in self._blocked_virtual_names:
            return None
        route = self._route_map.get(normalized_tool_name)
        if not route:
            if normalized_tool_name not in self._local_proxy_tools:
                return None
            normalized_args = self._normalize_arguments(normalized_tool_name, tool_input)
            return MCPToolRoute(
                adapter_name="local_proxy",
                mcp_tool_name=normalized_tool_name,
                arguments=normalized_args,
                is_write=False,
            )

        adapter_name, mcp_tool_name, is_write = route
        normalized_args = self._normalize_arguments(normalized_tool_name, tool_input)
        return MCPToolRoute(
            adapter_name=adapter_name,
            mcp_tool_name=mcp_tool_name,
            arguments=normalized_args,
            is_write=bool(is_write),
        )
