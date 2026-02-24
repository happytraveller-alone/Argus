from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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
        self._route_map = {
            "read_file": ("filesystem", "read_file", False),
            "list_files": ("filesystem", "list_directory", False),
            "search_code": ("code_index", "search_code_advanced", False),
            "extract_function": ("code_index", "get_symbol_body", False),
            "locate_enclosing_function": ("code_index", "get_file_summary", False),
            "qmd_query": ("qmd", "query", False),
            "qmd_get": ("qmd", "get", False),
            "qmd_multi_get": ("qmd", "multi_get", False),
            "qmd_status": ("qmd", "status", False),
            "memory_store": ("memory", "memory_store", False),
            "memory_query": ("memory", "memory_query", False),
            "memory_append": ("memory", "memory_append", False),
            "sequential_thinking": ("sequentialthinking", "sequential_thinking", False),
            "reasoning_trace": ("sequentialthinking", "reasoning_trace", False),
            "edit_file": ("filesystem", "edit_file", True),
            "write_file": ("filesystem", "write_file", True),
        }

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        return str(tool_name or "").strip().lower()

    @staticmethod
    def _normalize_arguments(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(tool_input or {})

        if tool_name == "search_code":
            keyword = payload.get("keyword")
            if isinstance(keyword, str) and keyword.strip() and "query" not in payload:
                payload["query"] = keyword.strip()
            directory = payload.get("directory")
            if isinstance(directory, str) and directory.strip() and "path" not in payload:
                payload["path"] = directory.strip()
            file_pattern = payload.get("file_pattern")
            if isinstance(file_pattern, str) and file_pattern.strip() and "glob" not in payload:
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
            file_path = payload.get("file_path") or payload.get("path")
            if isinstance(file_path, str) and file_path.strip():
                payload["path"] = file_path.strip()
            function_name = payload.get("function_name")
            if isinstance(function_name, str) and function_name.strip() and "symbol" not in payload:
                payload["symbol"] = function_name.strip()

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

        return payload

    def can_route(self, tool_name: str) -> bool:
        return self._normalize_tool_name(tool_name) in self._route_map

    def is_write_tool(self, tool_name: str) -> bool:
        normalized = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized)
        return bool(route and route[2])

    def route(self, tool_name: str, tool_input: Dict[str, Any]) -> Optional[MCPToolRoute]:
        normalized_tool_name = self._normalize_tool_name(tool_name)
        route = self._route_map.get(normalized_tool_name)
        if not route:
            return None

        adapter_name, mcp_tool_name, is_write = route
        normalized_args = self._normalize_arguments(normalized_tool_name, tool_input)
        return MCPToolRoute(
            adapter_name=adapter_name,
            mcp_tool_name=mcp_tool_name,
            arguments=normalized_args,
            is_write=bool(is_write),
        )
