from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

LANGUAGE_ALIASES = {
    "c#": "csharp",
    "c++": "cpp",
    "golang": "go",
    "js": "javascript",
    "py": "python",
    "shell": "bash",
    "ts": "typescript",
}

FUNCTION_LIKE_TYPES = {
    "arrow_function",
    "constructor_declaration",
    "function",
    "function_declaration",
    "function_definition",
    "function_item",
    "function_expression",
    "func_literal",
    "generator_function_declaration",
    "lambda_expression",
    "method",
    "method_declaration",
    "method_definition",
}

IDENTIFIER_TYPES = {
    "field_identifier",
    "identifier",
    "private_property_identifier",
    "property_identifier",
    "shorthand_property_identifier",
    "type_identifier",
}


def _normalize_language(language: str) -> str:
    raw = str(language or "").strip().lower().replace("-", "_")
    return LANGUAGE_ALIASES.get(raw, raw)


def _load_tree_sitter_parser(language: str):
    normalized = _normalize_language(language)
    if not normalized:
        return None
    try:
        from tree_sitter_language_pack import get_parser
    except Exception:
        return None
    try:
        return get_parser(normalized)
    except Exception:
        return None


def _iter_nodes(root_node: Any) -> Iterable[Any]:
    stack = [root_node]
    while stack:
        node = stack.pop()
        yield node
        children = list(getattr(node, "named_children", []) or [])
        stack.extend(reversed(children))


def _node_text(node: Any, source_bytes: bytes) -> str:
    try:
        start = int(getattr(node, "start_byte"))
        end = int(getattr(node, "end_byte"))
    except Exception:
        return ""
    if start < 0 or end < start:
        return ""
    return source_bytes[start:end].decode("utf-8", errors="replace")


def _find_identifier(node: Any, source_bytes: bytes) -> Optional[str]:
    if node is None:
        return None
    node_type = str(getattr(node, "type", "") or "")
    if node_type in IDENTIFIER_TYPES:
        text = _node_text(node, source_bytes).strip()
        return text or None
    for field_name in ("name", "declarator", "declaration", "left", "key", "property"):
        try:
            child = node.child_by_field_name(field_name)
        except Exception:
            child = None
        text = _find_identifier(child, source_bytes)
        if text:
            return text
    for child in list(getattr(node, "named_children", []) or []):
        text = _find_identifier(child, source_bytes)
        if text:
            return text
    return None


def _extract_callable_name(node: Any, source_bytes: bytes) -> Optional[str]:
    for field_name in ("name", "declarator", "definition"):
        try:
            child = node.child_by_field_name(field_name)
        except Exception:
            child = None
        text = _find_identifier(child, source_bytes)
        if text:
            return text

    parent = getattr(node, "parent", None)
    if parent is not None:
        parent_type = str(getattr(parent, "type", "") or "")
        if parent_type in {"assignment_expression", "pair", "variable_declarator"}:
            text = _find_identifier(parent, source_bytes)
            if text:
                return text

    snippet = _node_text(node, source_bytes)
    regex_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", snippet)
    if regex_match:
        return regex_match.group(1)
    return None


def _definition_kind(node_type: str) -> str:
    lowered = node_type.lower()
    if "method" in lowered or "constructor" in lowered:
        return "method"
    return "function"


def _is_function_like(node: Any) -> bool:
    node_type = str(getattr(node, "type", "") or "")
    if node_type in FUNCTION_LIKE_TYPES:
        return True
    lowered = node_type.lower()
    if lowered.endswith("_function") or lowered.endswith("_method"):
        return True
    return False


class TreeSitterParser:
    def parse(self, content: str, language: str):
        parser = _load_tree_sitter_parser(language)
        if parser is None:
            return None
        return parser.parse(str(content or "").encode("utf-8"))

    def extract_definitions(self, tree: Any, content: str, language: str) -> List[Dict[str, Any]]:
        root_node = getattr(tree, "root_node", None)
        if root_node is None:
            return []

        source_bytes = str(content or "").encode("utf-8")
        definitions: List[Dict[str, Any]] = []
        seen = set()

        for node in _iter_nodes(root_node):
            if not _is_function_like(node):
                continue
            name = _extract_callable_name(node, source_bytes)
            if not name:
                continue

            start_point = list(getattr(node, "start_point", (0, 0)) or (0, 0))
            end_point = list(getattr(node, "end_point", (0, 0)) or (0, 0))
            key = (name, tuple(start_point), tuple(end_point))
            if key in seen:
                continue
            seen.add(key)
            definitions.append(
                {
                    "name": name,
                    "type": _definition_kind(str(getattr(node, "type", "") or "")),
                    "start_point": start_point,
                    "end_point": end_point,
                    "language": _normalize_language(language),
                }
            )

        definitions.sort(key=lambda item: (item["start_point"][0], item["start_point"][1], item["name"]))
        return definitions
