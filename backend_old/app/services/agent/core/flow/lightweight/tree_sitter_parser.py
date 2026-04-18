"""
代码解析器 - 基于 Tree-sitter AST 的代码解析
提供中性的 AST 级别的代码分析能力
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TreeSitterParser:
    """
    基于 Tree-sitter 的代码解析器
    提供 AST 级别的代码分析
    """

    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".kt": "kotlin",
        ".swift": "swift",
    }

    DEFINITION_TYPES = {
        "python": {
            "class": ["class_definition"],
            "function": ["function_definition"],
            "method": ["function_definition"],
            "import": ["import_statement", "import_from_statement"],
        },
        "javascript": {
            "class": ["class_declaration", "class"],
            "function": ["function_declaration", "function", "arrow_function", "method_definition"],
            "import": ["import_statement"],
        },
        "typescript": {
            "class": ["class_declaration", "class"],
            "function": ["function_declaration", "function", "arrow_function", "method_definition"],
            "interface": ["interface_declaration"],
            "import": ["import_statement"],
        },
        "java": {
            "class": ["class_declaration"],
            "method": ["method_declaration", "constructor_declaration"],
            "interface": ["interface_declaration"],
            "import": ["import_declaration"],
        },
        "kotlin": {
            "class": ["class_declaration"],
            "function": ["function_declaration"],
            "interface": ["class_declaration"],
            "import": ["import_header"],
        },
        "c": {
            "function": ["function_definition"],
        },
        "cpp": {
            "function": ["function_definition"],
        },
        "go": {
            "struct": ["type_declaration"],
            "function": ["function_declaration", "method_declaration"],
            "interface": ["type_declaration"],
            "import": ["import_declaration"],
        },
    }

    SUPPORTED_LANGUAGES = {
        "python",
        "javascript",
        "typescript",
        "tsx",
        "java",
        "go",
        "rust",
        "c",
        "cpp",
        "csharp",
        "php",
        "ruby",
        "kotlin",
        "swift",
        "bash",
        "json",
        "yaml",
        "html",
        "css",
        "sql",
        "markdown",
    }

    def __init__(self):
        self._parsers: dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self, language: str) -> bool:
        if language in self._parsers:
            return True

        if language not in self.SUPPORTED_LANGUAGES:
            return False

        try:
            from tree_sitter_language_pack import get_parser

            parser = get_parser(language)
            self._parsers[language] = parser
            return True

        except ImportError:
            logger.warning("tree-sitter-languages not installed, falling back to regex parsing")
            return False
        except Exception as e:
            logger.warning(f"Failed to load tree-sitter parser for {language}: {e}")
            return False

    def parse(self, code: str, language: str) -> Any | None:
        if not self._ensure_initialized(language):
            return None

        parser = self._parsers.get(language)
        if not parser:
            return None

        try:
            tree = parser.parse(code.encode())
            return tree
        except Exception as e:
            logger.warning(f"Failed to parse code: {e}")
            return None

    async def parse_async(self, code: str, language: str) -> Any | None:
        return await asyncio.to_thread(self.parse, code, language)

    def extract_definitions(self, tree: Any, code: str, language: str) -> list[dict[str, Any]]:
        if tree is None:
            return []

        definitions = []
        definition_types = self.DEFINITION_TYPES.get(language, {})

        def traverse(node, parent_name=None):
            node_type = node.type

            matched = False
            for def_category, types in definition_types.items():
                if node_type in types:
                    name = self._extract_name(node, language)

                    actual_category = def_category
                    if def_category == "function" and parent_name:
                        actual_category = "method"
                    elif def_category == "method" and not parent_name:
                        continue

                    definitions.append(
                        {
                            "type": actual_category,
                            "name": name,
                            "parent_name": parent_name,
                            "start_point": node.start_point,
                            "end_point": node.end_point,
                            "start_byte": node.start_byte,
                            "end_byte": node.end_byte,
                            "node_type": node_type,
                        }
                    )

                    matched = True
                    if def_category == "class":
                        for child in node.children:
                            traverse(child, name)
                        return
                    break

            if not matched:
                for child in node.children:
                    traverse(child, parent_name)

        traverse(tree.root_node)
        return definitions

    def _extract_name(self, node: Any, language: str) -> str | None:
        for child in node.children:
            if child.type in [
                "identifier",
                "property_identifier",
                "type_identifier",
                "field_identifier",
                "name",
            ]:
                return child.text.decode("utf-8")

        if language == "python":
            for child in node.children:
                if child.type == "identifier":
                    return child.text.decode("utf-8")

        return None
