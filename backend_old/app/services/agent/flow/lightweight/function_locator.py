from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.core.config import settings
from app.services.flow_parser_runner import get_flow_parser_runner_client
from app.services.parser import TreeSitterParser

from .function_locator_cli import locate_with_tree_sitter_cli

logger = logging.getLogger(__name__)


_LANGUAGE_ALIASES = {
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "tsx",
    "py": "python",
    "kt": "kotlin",
    "kts": "kotlin",
    "cxx": "cpp",
    "cc": "cpp",
    "hpp": "cpp",
    "hxx": "cpp",
}

_EXT_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
}

_TARGET_NODE_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition"},
    "typescript": {"function_declaration", "method_definition"},
    "tsx": {"function_declaration", "method_definition"},
    "java": {"method_declaration", "constructor_declaration"},
    "kotlin": {"function_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
}

_PSEUDO_FUNCTION_NAMES = {"__attribute__", "__declspec"}


def _normalize_language_token(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not token:
        return None
    return _LANGUAGE_ALIASES.get(token, token)


def _normalize_allowed_languages(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for item in values:
        token = _normalize_language_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _is_pseudo_function_name(name: Optional[str]) -> bool:
    if not isinstance(name, str):
        return False
    normalized = name.strip().lower()
    return normalized in _PSEUDO_FUNCTION_NAMES


class EnclosingFunctionLocator:
    """Locate enclosing function for a file:line with Python tree-sitter first.

    Resolution order:
    1) Python tree-sitter binding (`tree_sitter_language_pack`)
    2) tree-sitter CLI fallback (best-effort, non-blocking)
    """

    def __init__(
        self,
        *,
        project_root: Optional[str] = None,
        allowed_languages: Optional[Iterable[str]] = None,
        cli_fallback_enabled: bool = True,
    ):
        configured = allowed_languages or getattr(settings, "FUNCTION_LOCATOR_LANGUAGES", [])
        normalized = _normalize_allowed_languages(configured)
        if not normalized:
            normalized = ["python", "javascript", "typescript", "java", "kotlin", "c", "cpp"]
        self.allowed_languages = set(normalized)
        self.project_root = Path(project_root).resolve() if project_root else None
        self.cli_fallback_enabled = bool(cli_fallback_enabled)
        self.parser = TreeSitterParser()
        self._definitions_cache: Dict[str, List[Dict[str, int | str]]] = {}

    def _detect_language(self, file_path: str) -> Optional[str]:
        ext = Path(file_path).suffix.lower()
        language = _EXT_LANGUAGE_MAP.get(ext)
        return _normalize_language_token(language)

    def _node_text(self, node: object, code_bytes: bytes) -> str:
        try:
            start_byte = int(getattr(node, "start_byte"))
            end_byte = int(getattr(node, "end_byte"))
            if end_byte <= start_byte:
                return ""
            return code_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_identifier_from_node(self, node: object, code_bytes: bytes) -> Optional[str]:
        node_type = str(getattr(node, "type", ""))
        if node_type in {
            "identifier",
            "field_identifier",
            "type_identifier",
            "property_identifier",
            "simple_identifier",
        }:
            text = self._node_text(node, code_bytes).strip()
            if text and not _is_pseudo_function_name(text):
                return text

        children = list(getattr(node, "children", []) or [])
        for child in children:
            value = self._extract_identifier_from_node(child, code_bytes)
            if value:
                return value
        return None

    def _extract_function_name(self, node: object, language: str, code_bytes: bytes) -> Optional[str]:
        try:
            field_name_node = node.child_by_field_name("name")
        except Exception:
            field_name_node = None

        if field_name_node is not None:
            candidate = self._extract_identifier_from_node(field_name_node, code_bytes)
            if candidate and not _is_pseudo_function_name(candidate):
                return candidate

        if language in {"kotlin"}:
            children = list(getattr(node, "children", []) or [])
            for child in children:
                child_type = str(getattr(child, "type", ""))
                if child_type in {"identifier", "simple_identifier"}:
                    candidate = self._node_text(child, code_bytes).strip()
                    if candidate and not _is_pseudo_function_name(candidate):
                        return candidate

        if language in {"c", "cpp"}:
            try:
                declarator = node.child_by_field_name("declarator")
            except Exception:
                declarator = None
            if declarator is not None:
                candidate = self._extract_identifier_from_node(declarator, code_bytes)
                if candidate and not _is_pseudo_function_name(candidate):
                    return candidate
            for child in list(getattr(node, "children", []) or []):
                child_type = str(getattr(child, "type", ""))
                if child_type.endswith("declarator"):
                    candidate = self._extract_identifier_from_node(child, code_bytes)
                    if candidate and not _is_pseudo_function_name(candidate):
                        return candidate

        candidate = self._extract_identifier_from_node(node, code_bytes)
        if candidate and not _is_pseudo_function_name(candidate):
            return candidate
        return None

    def _extract_definitions(self, *, file_path: str, language: str, code: str) -> List[Dict[str, int | str]]:
        cached = self._definitions_cache.get(file_path)
        if cached is not None:
            return cached

        definitions: List[Dict[str, int | str]] = []
        node_types = _TARGET_NODE_TYPES.get(language, set())
        if not node_types:
            self._definitions_cache[file_path] = definitions
            return definitions

        tree = self.parser.parse(code, language)
        if tree is None:
            self._definitions_cache[file_path] = definitions
            return definitions

        code_bytes = code.encode("utf-8", errors="replace")
        root_node = tree.root_node
        stack = [root_node]

        while stack:
            node = stack.pop()
            node_type = str(getattr(node, "type", ""))
            if node_type in node_types:
                name = self._extract_function_name(node, language, code_bytes)
                if name and not _is_pseudo_function_name(name):
                    start_line = int(node.start_point[0]) + 1
                    end_line = int(node.end_point[0]) + 1
                    if end_line < start_line:
                        end_line = start_line
                    definitions.append(
                        {
                            "name": name,
                            "start_line": start_line,
                            "end_line": end_line,
                        }
                    )
            stack.extend(reversed(list(getattr(node, "children", []) or [])))

        self._definitions_cache[file_path] = definitions
        return definitions

    def _resolve_relative_path(self, full_path: str) -> str:
        if not self.project_root:
            return str(full_path).replace("\\", "/")
        try:
            rel = Path(full_path).resolve().relative_to(self.project_root)
            return str(rel).replace("\\", "/")
        except Exception:
            return str(full_path).replace("\\", "/")

    def locate(
        self,
        *,
        full_file_path: str,
        line_start: int,
        relative_file_path: Optional[str] = None,
        file_lines: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        diagnostics: List[str] = []
        file_path = str(full_file_path)
        language = _normalize_language_token(self._detect_language(file_path))

        if not language:
            return {
                "file_path": relative_file_path or self._resolve_relative_path(file_path),
                "function": None,
                "start_line": None,
                "end_line": None,
                "resolution_method": "missing_enclosing_function",
                "resolution_engine": "unsupported_language",
                "language": None,
                "diagnostics": ["unknown_language"],
            }

        if language not in self.allowed_languages:
            return {
                "file_path": relative_file_path or self._resolve_relative_path(file_path),
                "function": None,
                "start_line": None,
                "end_line": None,
                "resolution_method": "missing_enclosing_function",
                "resolution_engine": "language_disabled",
                "language": language,
                "diagnostics": [f"language_not_enabled:{language}"],
            }

        try:
            code = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            diagnostics.append(f"file_read_failed:{type(exc).__name__}")
            return {
                "file_path": relative_file_path or self._resolve_relative_path(file_path),
                "function": None,
                "start_line": None,
                "end_line": None,
                "resolution_method": "missing_enclosing_function",
                "resolution_engine": "file_read_failed",
                "language": language,
                "diagnostics": diagnostics,
            }

        try:
            runner_client = get_flow_parser_runner_client()
            runner_result = runner_client.locate_enclosing_function(
                file_path=relative_file_path or self._resolve_relative_path(file_path),
                line_start=int(max(1, line_start)),
                language=language,
                content=code,
            )
        except Exception as exc:
            diagnostics.append(f"flow_parser_runner_error:{type(exc).__name__}")
            runner_result = None

        if isinstance(runner_result, dict):
            runner_function = str(runner_result.get("function") or "").strip()
            if runner_function and not _is_pseudo_function_name(runner_function):
                runner_diagnostics = runner_result.get("diagnostics")
                merged_diagnostics = list(diagnostics)
                merged_diagnostics.append("flow_parser_runner")
                if isinstance(runner_diagnostics, list):
                    merged_diagnostics.extend(str(item) for item in runner_diagnostics if str(item))
                return {
                    "file_path": relative_file_path or self._resolve_relative_path(file_path),
                    "function": runner_function,
                    "start_line": runner_result.get("start_line"),
                    "end_line": runner_result.get("end_line"),
                    "resolution_method": str(runner_result.get("resolution_method") or "python_tree_sitter"),
                    "resolution_engine": str(runner_result.get("resolution_engine") or "python_tree_sitter"),
                    "language": runner_result.get("language") or language,
                    "diagnostics": merged_diagnostics,
                }

        try:
            definitions = self._extract_definitions(
                file_path=file_path,
                language=language,
                code=code,
            )
        except Exception as exc:
            logger.warning("[FunctionLocator] tree-sitter extraction failed (%s): %s", file_path, exc)
            diagnostics.append(f"tree_sitter_extract_failed:{type(exc).__name__}")
            definitions = []

        line_number = int(max(1, line_start))
        candidates = [
            item
            for item in definitions
            if int(item["start_line"]) <= line_number <= int(item["end_line"])
        ]
        if candidates:
            best = min(
                candidates,
                key=lambda item: (
                    max(0, int(item["end_line"]) - int(item["start_line"])),
                    int(item["start_line"]),
                ),
            )
            return {
                "file_path": relative_file_path or self._resolve_relative_path(file_path),
                "function": str(best["name"]),
                "start_line": int(best["start_line"]),
                "end_line": int(best["end_line"]),
                "resolution_method": "python_tree_sitter",
                "resolution_engine": "python_tree_sitter",
                "language": language,
                "diagnostics": diagnostics,
            }

        diagnostics.append("python_tree_sitter_no_enclosing_symbol")
        if self.cli_fallback_enabled:
            cli_result = locate_with_tree_sitter_cli(
                file_path=file_path,
                line_start=line_number,
                language=language,
                file_lines=file_lines,
            )
            cli_diagnostics = cli_result.get("diagnostics")
            if isinstance(cli_diagnostics, list):
                diagnostics.extend(str(item) for item in cli_diagnostics if str(item))

            function_name = cli_result.get("function")
            if isinstance(function_name, str) and function_name.strip() and not _is_pseudo_function_name(function_name):
                return {
                    "file_path": relative_file_path or self._resolve_relative_path(file_path),
                    "function": function_name.strip(),
                    "start_line": cli_result.get("start_line"),
                    "end_line": cli_result.get("end_line"),
                    "resolution_method": str(cli_result.get("resolution_method") or "tree_sitter_cli_regex"),
                    "resolution_engine": str(cli_result.get("resolution_engine") or "tree_sitter_cli_regex"),
                    "language": language,
                    "diagnostics": diagnostics,
                }

        return {
            "file_path": relative_file_path or self._resolve_relative_path(file_path),
            "function": None,
            "start_line": None,
            "end_line": None,
            "resolution_method": "missing_enclosing_function",
            "resolution_engine": "missing_enclosing_function",
            "language": language,
            "diagnostics": diagnostics,
        }
