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

    # 语言映射
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

    # 各语言的函数/类节点类型
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

    # tree-sitter-languages 支持的语言列表
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
        """确保语言解析器已初始化"""
        if language in self._parsers:
            return True

        # 检查语言是否受支持
        if language not in self.SUPPORTED_LANGUAGES:
            # 不是 tree-sitter 支持的语言，静默跳过
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
        """解析代码返回 AST（同步方法）"""
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
        """
        异步解析代码返回 AST

        将 CPU 密集型的 Tree-sitter 解析操作放到线程池中执行，
        避免阻塞事件循环
        """
        return await asyncio.to_thread(self.parse, code, language)

    def extract_definitions(self, tree: Any, code: str, language: str) -> list[dict[str, Any]]:
        """从 AST 提取定义"""
        if tree is None:
            return []

        definitions = []
        definition_types = self.DEFINITION_TYPES.get(language, {})

        def traverse(node, parent_name=None):
            node_type = node.type

            # 检查是否是定义节点
            matched = False
            for def_category, types in definition_types.items():
                if node_type in types:
                    name = self._extract_name(node, language)

                    # 根据是否有 parent_name 来区分 function 和 method
                    actual_category = def_category
                    if def_category == "function" and parent_name:
                        actual_category = "method"
                    elif def_category == "method" and not parent_name:
                        # 跳过没有 parent 的 method 定义（由 function 类别处理）
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

                    # 对于类，继续遍历子节点找方法
                    if def_category == "class":
                        for child in node.children:
                            traverse(child, name)
                        return

                    # 匹配到一个类别后就不再匹配其他类别
                    break

            # 如果没有匹配到定义，继续遍历子节点
            if not matched:
                for child in node.children:
                    traverse(child, parent_name)

        traverse(tree.root_node)
        return definitions

    def _extract_name(self, node: Any, language: str) -> str | None:
        """从节点提取名称（避免 C/C++ attribute 误判为函数名）。"""

        def _node_text(target: Any) -> str:
            value = target.text.decode() if isinstance(target.text, bytes) else target.text
            return str(value or "").strip()

        def _is_valid_name(name: str) -> bool:
            lowered = str(name or "").strip().lower()
            if not lowered:
                return False
            if lowered in {"__attribute__", "__declspec"}:
                return False
            return True

        def _extract_identifier_recursive(target: Any) -> str | None:
            node_type = str(getattr(target, "type", ""))
            if node_type in {
                "identifier",
                "name",
                "type_identifier",
                "property_identifier",
                "simple_identifier",
                "field_identifier",
            }:
                candidate = _node_text(target)
                if _is_valid_name(candidate):
                    return candidate

            children = list(getattr(target, "children", []) or [])
            for child in children:
                candidate = _extract_identifier_recursive(child)
                if candidate:
                    return candidate
            return None

        try:
            field_name = node.child_by_field_name("name")
        except Exception:
            field_name = None
        if field_name is not None:
            candidate = _extract_identifier_recursive(field_name)
            if candidate:
                return candidate

        if language in {"c", "cpp"}:
            try:
                declarator = node.child_by_field_name("declarator")
            except Exception:
                declarator = None
            if declarator is not None:
                candidate = _extract_identifier_recursive(declarator)
                if candidate:
                    return candidate
            for child in list(getattr(node, "children", []) or []):
                if str(getattr(child, "type", "")).endswith("declarator"):
                    candidate = _extract_identifier_recursive(child)
                    if candidate:
                        return candidate

        return _extract_identifier_recursive(node)
