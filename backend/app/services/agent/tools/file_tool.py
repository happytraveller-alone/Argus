"""
文件操作工具
读取和搜索代码文件
"""

import os
import re
import fnmatch
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator

from app.services.agent.flow.lightweight.function_locator import EnclosingFunctionLocator

from .base import AgentTool, ToolResult
from .evidence_protocol import (
    build_display_command as _build_display_command,
    build_structured_lines as _build_structured_lines,
    detect_language as _detect_language,
    format_structured_lines_for_code_block as _format_structured_lines_for_code_block,
    format_structured_lines_for_search as _format_structured_lines_for_search,
    unique_command_chain as _unique_command_chain,
    validate_evidence_metadata as _validate_evidence_metadata,
)


def _normalize_rel_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _has_hidden_or_test_segment(path: str) -> bool:
    normalized = _normalize_rel_path(path)
    if not normalized:
        return False
    parts = [part for part in normalized.split("/") if part]
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in {"test", "tests"}:
            return True
        if part.startswith("."):
            return True
    return False


def _parse_file_path_with_line_range(file_path: str) -> tuple[str, Optional[int], Optional[int]]:
    """解析 file_path:line 或 file_path:start-end 形式。"""
    raw = str(file_path or "").strip()
    if not raw:
        return raw, None, None

    match = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", raw)
    if not match:
        return raw, None, None

    parsed_path = (match.group(1) or "").strip()
    if not parsed_path:
        return raw, None, None

    start_line = int(match.group(2))
    end_line = int(match.group(3)) if match.group(3) else start_line
    if end_line < start_line:
        start_line, end_line = end_line, start_line

    return parsed_path, start_line, end_line


def _split_file_patterns(file_pattern: Optional[Any]) -> List[str]:
    """支持 *.c|*.h / *.c,*.h / *.c;*.h 多模式。"""
    if file_pattern is None:
        return []

    if isinstance(file_pattern, list):
        normalized = [str(item).strip() for item in file_pattern if str(item).strip()]
        return normalized

    text = str(file_pattern).strip()
    if not text:
        return []

    parts = [item.strip() for item in re.split(r"[|,;]", text) if item.strip()]
    return parts or [text]


_SOURCE_FILE_EXTENSIONS = (
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".go", ".rs", ".php", ".rb", ".swift",
    ".kt", ".m", ".mm", ".cs", ".scala",
)

_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
}


def _is_source_like_file(path_value: str) -> bool:
    ext = Path(str(path_value or "")).suffix.lower()
    return ext in _SOURCE_FILE_EXTENSIONS


def _detect_language(path_value: str) -> str:
    ext = os.path.splitext(str(path_value or ""))[1].lower()
    return _LANGUAGE_BY_EXTENSION.get(ext, "text")


def _unique_command_chain(commands: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in commands:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _build_display_command(command_chain: List[str]) -> str:
    normalized = _unique_command_chain(command_chain)
    return " -> ".join(normalized) if normalized else "python"


def _build_structured_lines(
    selected_lines: List[str],
    start_line: int,
    focus_start_line: int,
    focus_end_line: int,
    focus_kind: str,
) -> List[Dict[str, Any]]:
    structured: List[Dict[str, Any]] = []
    for index, raw_line in enumerate(selected_lines):
        line_number = start_line + index
        kind = focus_kind if focus_start_line <= line_number <= focus_end_line else "context"
        structured.append(
            {
                "line_number": line_number,
                "text": str(raw_line).rstrip("\n"),
                "kind": kind,
            }
        )
    return structured


def _format_structured_lines_for_code_block(lines: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"{int(item['line_number']):4d}| {str(item.get('text') or '')}"
        for item in lines
    )


def _format_structured_lines_for_search(lines: List[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for item in lines:
        line_number = int(item["line_number"])
        prefix = ">" if item.get("kind") == "match" else " "
        rows.append(f"{prefix} {line_number:4d}| {str(item.get('text') or '')}")
    return "\n".join(rows)


def _validate_evidence_metadata(
    *,
    render_type: str,
    command_chain: List[str],
    display_command: str,
    entries: List[Dict[str, Any]],
) -> None:
    if render_type not in {
        "code_window",
        "search_hits",
        "outline_summary",
        "function_summary",
        "symbol_body",
    }:
        raise ValueError(f"unsupported render_type: {render_type}")
    if not isinstance(command_chain, list) or not command_chain:
        raise ValueError("command_chain is required")
    if not isinstance(display_command, str) or not display_command.strip():
        raise ValueError("display_command is required")
    if entries is None:
        raise ValueError("entries is required")

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("entry must be an object")
        if render_type == "search_hits":
            if not str(entry.get("file_path") or "").strip():
                raise ValueError("entry.file_path is required")
            if not isinstance(entry.get("match_line"), int):
                raise ValueError("entry.match_line is required")
            if "match_text" not in entry:
                raise ValueError("entry.match_text is required")
            continue

        if render_type in {"outline_summary", "function_summary"}:
            if not str(entry.get("file_path") or "").strip():
                raise ValueError("entry.file_path is required")
            continue

        if not str(entry.get("file_path") or "").strip():
            raise ValueError("entry.file_path is required")
        if not isinstance(entry.get("lines"), list):
            raise ValueError("entry.lines is required")
        for line in entry["lines"]:
            if not isinstance(line, dict):
                raise ValueError("line must be an object")
            if not isinstance(line.get("line_number"), int):
                raise ValueError("line.line_number is required")
            if "text" not in line:
                raise ValueError("line.text is required")
            if str(line.get("kind") or "").strip() not in {"context", "focus", "match"}:
                raise ValueError("line.kind is invalid")


def _normalize_reason_path(path_value: Any, project_root: str) -> Optional[str]:
    text = str(path_value or "").strip().replace("\\", "/")
    if not text:
        return None
    candidate = text
    if os.path.isabs(candidate):
        try:
            rel = os.path.relpath(candidate, project_root).replace("\\", "/")
            if rel.startswith(".."):
                return None
            candidate = rel
        except Exception:
            return None
    candidate = _normalize_rel_path(candidate)
    if not candidate:
        return None
    if "." in os.path.basename(candidate):
        candidate = _normalize_rel_path(os.path.dirname(candidate))
    return candidate or None


def _normalize_display_path(path_value: str, project_root: str) -> str:
    text = str(path_value or "").strip().replace("\\", "/")
    if not text:
        return text
    if os.path.isabs(text):
        try:
            rel = os.path.relpath(text, project_root).replace("\\", "/")
            if not rel.startswith(".."):
                return _normalize_rel_path(rel)
        except Exception:
            pass
        return os.path.basename(text)
    return _normalize_rel_path(text)


def _is_path_within_root(candidate_path: str, root_path: str) -> bool:
    try:
        return os.path.commonpath(
            [os.path.normpath(candidate_path), os.path.normpath(root_path)]
        ) == os.path.normpath(root_path)
    except Exception:
        return False


def _resolve_project_file(
    *,
    project_root: str,
    file_path: str,
    target_files: Optional[set[str]] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    requested = str(file_path or "").strip()
    parsed_path, _start, _end = _parse_file_path_with_line_range(requested)
    candidate = parsed_path or requested
    if not candidate:
        return None, None, "必须提供 file_path"

    if os.path.isabs(candidate):
        full_path = os.path.normpath(candidate)
        if not _is_path_within_root(full_path, project_root):
            return None, None, "安全错误：不允许访问项目目录外的文件"
        relative_path = _normalize_rel_path(
            os.path.relpath(full_path, project_root).replace("\\", "/")
        )
    else:
        relative_path = _normalize_rel_path(candidate)
        full_path = os.path.normpath(os.path.join(project_root, relative_path))
        if not _is_path_within_root(full_path, project_root):
            return None, None, "安全错误：不允许访问项目目录外的文件"

    if not relative_path:
        return None, None, "必须提供 file_path"
    if target_files and relative_path not in target_files:
        return None, None, f"文件不在目标范围内: {relative_path}"
    if not os.path.exists(full_path):
        return None, None, f"文件不存在: {relative_path}"
    if not os.path.isfile(full_path):
        return None, None, f"不是文件: {relative_path}"
    return relative_path, full_path, None


def _read_text_sync(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_lines_sync(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def _infer_framework_hints(text: str, file_path: str = "") -> List[str]:
    lowered = str(text or "").lower()
    language = _detect_language(file_path)
    hints: List[str] = []

    if language == "java":
        spring_tokens = (
            "org.springframework",
            "@springbootapplication",
            "@restcontroller",
            "@controller",
            "@requestmapping",
            "@getmapping",
            "@postmapping",
            "springapplication.run",
        )
        if any(token in lowered for token in spring_tokens):
            hints.append("spring")
        return hints

    if language in {"javascript", "typescript"}:
        if any(token in lowered for token in ("from 'express'", 'from "express"', "require('express')", 'require("express")', "express()")):
            hints.append("express")
        if any(token in lowered for token in ("from 'react'", 'from "react"', "react.", "jsx", "tsx")):
            hints.append("react")
        if any(token in lowered for token in ("from 'vue'", 'from "vue"', "createapp(", "definecomponent(")):
            hints.append("vue")
        return hints

    if language == "python":
        for label, tokens in {
            "django": ("import django", "from django", "django.", "django.apps"),
            "flask": ("from flask", "import flask", "flask(", "blueprint("),
            "fastapi": ("from fastapi", "import fastapi", "fastapi(", "apirouter("),
        }.items():
            if any(token in lowered for token in tokens):
                hints.append(label)
        return hints

    return hints


def _extract_risk_markers(text: str) -> List[str]:
    patterns = {
        "command_execution": r"\b(os\.system|subprocess|exec|eval|Runtime\.getRuntime|system\()",
        "sql_execution": r"\b(cursor\.execute|executeQuery|raw\(|sequelize\.query|SELECT\s)",
        "deserialization": r"\b(pickle\.loads|yaml\.load|ObjectInputStream|unserialize\()",
        "file_access": r"\b(open\(|FileInputStream|fs\.readFile|send_file\()",
        "network_access": r"\b(requests\.|fetch\(|axios\.|http\.|urllib\.)",
    }
    markers: List[str] = []
    for label, pattern in patterns.items():
        if re.search(pattern, str(text or ""), re.IGNORECASE):
            markers.append(label)
    return markers


def _extract_key_calls(text: str, limit: int = 8) -> List[str]:
    stopwords = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "print",
        "len",
        "range",
        "str",
        "int",
        "list",
        "dict",
    }
    calls: List[str] = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", str(text or "")):
        candidate = str(match.group(1) or "").strip()
        if not candidate:
            continue
        base = candidate.split(".")[-1].lower()
        if base in stopwords or candidate in calls:
            continue
        calls.append(candidate)
        if len(calls) >= limit:
            break
    return calls


def _extract_related_symbols(text: str, limit: int = 8) -> List[str]:
    symbols: List[str] = []
    for pattern in (
        r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*(?:function\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
    ):
        for match in re.finditer(pattern, str(text or ""), re.MULTILINE):
            candidate = str(match.group(1) or "").strip()
            if not candidate or candidate in symbols:
                continue
            symbols.append(candidate)
            if len(symbols) >= limit:
                return symbols
    return symbols


class FileReadInput(BaseModel):
    """文件读取输入"""
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    start_line: Optional[int] = Field(default=None, description="起始行号（从1开始）")
    end_line: Optional[int] = Field(default=None, description="结束行号")
    max_lines: int = Field(default=500, description="最大返回行数")
    project_scope: bool = Field(default=False, description="允许基于项目范围补全 basename 路径")


class FileReadTool(AgentTool):
    """
    文件读取工具
    读取项目中的文件内容
    """
    
    def __init__(
        self, 
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        """
        初始化文件读取工具
        
        Args:
            project_root: 项目根目录
            exclude_patterns: 排除模式列表
            target_files: 目标文件列表（如果指定，只允许读取这些文件）
        """
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = set(target_files) if target_files else None
        self._project_scope_index: Optional[Dict[str, List[str]]] = None

    @staticmethod
    def _read_window_and_count_sync(
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> tuple[List[str], int]:
        selected_lines: List[str] = []
        total_lines = 0
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for total_lines, raw_line in enumerate(f, start=1):
                if start_line <= total_lines <= end_line:
                    selected_lines.append(raw_line.rstrip("\n"))
        return selected_lines, total_lines

    def _build_project_scope_index_sync(self) -> Dict[str, List[str]]:
        index: Dict[str, List[str]] = {}
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                rel_path = _normalize_rel_path(
                    os.path.relpath(os.path.join(root, filename), self.project_root).replace("\\", "/")
                )
                if self._should_exclude(rel_path):
                    continue
                index.setdefault(filename, []).append(rel_path)
        return index

    async def _resolve_project_scope_match(self, file_path: str) -> Optional[str]:
        basename = os.path.basename(str(file_path or "").strip())
        if not basename:
            return None
        if self._project_scope_index is None:
            self._project_scope_index = await asyncio.to_thread(self._build_project_scope_index_sync)
        matches = self._project_scope_index.get(basename) or []
        if len(matches) == 1:
            return matches[0]
        return None

    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return """读取项目中的文件内容。

使用场景:
- 查看完整的源代码文件
- 查看特定行范围的代码
- 获取配置文件内容

输入:
- file_path: 文件路径（相对于项目根目录）
- start_line: 可选，起始行号
- end_line: 可选，结束行号
- max_lines: 最大返回行数（默认500）

输出格式: 每行代码前带有文件中的原始行号，格式为 `行号| 代码`，例如：
```
   4| def world():
   5|     return 42
```
可直接引用行号定位代码位置。

注意: 为避免输出过长，建议指定行范围搜索定位代码。"""
    
    @property
    def args_schema(self):
        return FileReadInput
    
    def _should_exclude(self, file_path: str) -> bool:
        """检查文件是否应该被排除"""
        # 如果指定了目标文件，只允许读取这些文件
        if self.target_files and file_path not in self.target_files:
            return True
        
        # 检查排除模式
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
            # 也检查文件名
            if fnmatch.fnmatch(os.path.basename(file_path), pattern):
                return True
        
        return False

    async def _execute(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_lines: int = 500,
        project_scope: bool = False,
        **kwargs
    ) -> ToolResult:
        """执行文件读取"""
        try:
            parsed_path, parsed_start_line, parsed_end_line = _parse_file_path_with_line_range(file_path)
            if parsed_path:
                file_path = parsed_path
            if start_line is None and parsed_start_line is not None:
                start_line = parsed_start_line
            if end_line is None and parsed_end_line is not None:
                end_line = parsed_end_line

            requested_path = str(file_path or "").strip()
            candidate_path = requested_path
            if os.path.isabs(candidate_path):
                full_path = os.path.realpath(candidate_path)
            else:
                full_path = os.path.realpath(os.path.join(self.project_root, candidate_path))

            root_path = os.path.realpath(self.project_root)
            if not full_path.startswith(root_path):
                return ToolResult(
                    success=False,
                    error="安全错误：不允许访问项目目录外的文件",
                )

            display_path = _normalize_display_path(candidate_path, self.project_root)
            if project_scope and not os.path.exists(full_path):
                scoped_match = await self._resolve_project_scope_match(display_path or candidate_path)
                if scoped_match:
                    display_path = scoped_match
                    full_path = os.path.realpath(os.path.join(self.project_root, scoped_match))

            # 检查是否被排除
            if self._should_exclude(display_path or requested_path):
                return ToolResult(
                    success=False,
                    error=f"文件被排除或不在目标文件列表中: {display_path or requested_path}",
                )

            if not os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {display_path or requested_path}",
                )
            
            if not os.path.isfile(full_path):
                return ToolResult(
                    success=False,
                    error=f"不是文件: {display_path or requested_path}",
                )
            
            # 检查文件大小
            file_size = os.path.getsize(full_path)
            is_large_file = file_size > 1024 * 1024  # 1MB
            
            if is_large_file and start_line is None and end_line is None:
                return ToolResult(
                    success=False,
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，请指定 start_line 和 end_line 读取部分内容",
                )
            
            if start_line is not None:
                start_idx = max(0, start_line - 1)
            else:
                start_idx = 0

            requested_start_line = start_idx + 1
            requested_end_line = (
                max(requested_start_line, int(end_line))
                if end_line is not None
                else requested_start_line + max(1, int(max_lines)) - 1
            )

            selected_lines, total_lines = await asyncio.to_thread(
                self._read_window_and_count_sync,
                full_path,
                requested_start_line,
                requested_end_line,
            )
            end_idx = min(total_lines, requested_end_line)
            command_chain = ["read_file"]

            focus_line = start_idx + 1 if total_lines > 0 else 1
            structured_lines = _build_structured_lines(
                selected_lines=selected_lines,
                start_line=start_idx + 1,
                focus_start_line=focus_line,
                focus_end_line=focus_line,
                focus_kind="focus",
            )
            language = _detect_language(display_path or requested_path)
            entries = [
                {
                    "file_path": display_path or requested_path,
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "focus_line": focus_line,
                    "language": language,
                    "lines": structured_lines,
                }
            ]
            command_chain = _unique_command_chain(command_chain)
            display_command = _build_display_command(command_chain)
            _validate_evidence_metadata(
                render_type="code_window",
                command_chain=command_chain,
                display_command=display_command,
                entries=entries,
            )

            content = _format_structured_lines_for_code_block(structured_lines)
            output = f"文件: {display_path or requested_path}\n"
            output += f"行数: {start_idx + 1}-{end_idx} / {total_lines}\n\n"
            output += f"```{language}\n{content}\n```"
            
            if end_idx < total_lines:
                output += f"\n\n... 还有 {total_lines - end_idx} 行未显示"
            
            return ToolResult(
                success=True,
                data=output,
                metadata={
                    "file_path": display_path or requested_path,
                    "total_lines": total_lines,
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "language": language,
                    "render_type": "code_window",
                    "command_chain": command_chain,
                    "display_command": display_command,
                    "entries": entries,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"读取文件失败: {str(e)}",
            )


class FileSearchInput(BaseModel):
    """文件搜索输入"""
    keyword: str = Field(description="搜索关键字或正则表达式")
    file_path: Optional[str] = Field(default=None, description="可选，限定搜索到单个文件（相对项目根目录）")
    path: Optional[str] = Field(default=None, description="兼容字段：可选，限定搜索到单个文件")
    file_pattern: Optional[str] = Field(default=None, description="文件名模式，如 *.py, *.js")
    directory: Optional[str] = Field(default=None, description="搜索目录（相对路径）")
    case_sensitive: bool = Field(default=False, description="是否区分大小写")
    max_results: int = Field(default=10, description="最大结果数，默认不超过 10 条")
    is_regex: bool = Field(default=False, description="是否使用正则表达式")

    @model_validator(mode="after")
    def normalize_single_file_alias(self) -> "FileSearchInput":
        if str(self.file_path or "").strip():
            return self
        alias = str(self.path or "").strip()
        if alias:
            self.file_path = alias
        return self


class FileSearchTool(AgentTool):
    """
    文件搜索工具
    在项目中搜索包含特定内容的代码
    """
    
    # 排除的目录
    DEFAULT_EXCLUDE_DIRS = {
        "node_modules", "vendor", "dist", "build", ".git",
        "__pycache__", ".pytest_cache", "coverage", ".nyc_output",
        ".vscode", ".idea", ".vs", "target", "venv", "env", "test", "tests",
    }
    
    def __init__(
        self, 
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )

        # 从 exclude_patterns 中提取目录排除
        self.exclude_dirs = set(self.DEFAULT_EXCLUDE_DIRS)
        for pattern in self.exclude_patterns:
            if pattern.endswith("/**"):
                self.exclude_dirs.add(pattern[:-3])
            elif "/" not in pattern and "*" not in pattern:
                self.exclude_dirs.add(pattern)

    @staticmethod
    def _read_file_lines_sync(file_path: str) -> List[str]:
        return _read_lines_sync(file_path)

    def _normalize_directory(self, directory: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        root_norm = os.path.normpath(self.project_root)
        raw = str(directory or "").strip().replace("\\", "/")
        if not raw or raw == ".":
            return ".", self.project_root, None

        if os.path.isabs(raw):
            search_dir = os.path.normpath(raw)
            if not _is_path_within_root(search_dir, root_norm):
                return None, None, "安全错误：不允许搜索项目目录外的内容"
            rel = os.path.relpath(search_dir, self.project_root).replace("\\", "/")
            rel = "." if rel == "." else _normalize_rel_path(rel)
        else:
            rel = _normalize_rel_path(raw)
            search_dir = os.path.normpath(os.path.join(self.project_root, rel))
            if not _is_path_within_root(search_dir, root_norm):
                return None, None, "安全错误：不允许搜索项目目录外的内容"

        if not os.path.exists(search_dir):
            return None, None, f"目录不存在: {raw or rel}"
        if not os.path.isdir(search_dir):
            return None, None, f"不是目录: {raw or rel}"

        return rel, search_dir, None

    def _should_skip_candidate(self, relative_path: str, filename: str) -> bool:
        if not relative_path:
            return True
        if _has_hidden_or_test_segment(relative_path):
            return True
        if self.target_files and relative_path not in self.target_files:
            return True
        for excl_pattern in self.exclude_patterns:
            if fnmatch.fnmatch(relative_path, excl_pattern):
                return True
            if fnmatch.fnmatch(filename, excl_pattern):
                return True
        return False

    def _resolve_single_file_target(self, raw_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        requested = str(raw_path or "").strip()
        parsed_path, _start, _end = _parse_file_path_with_line_range(requested)
        candidate = parsed_path or requested
        if not candidate:
            return None, None, "必须提供 file_path"

        if os.path.isabs(candidate):
            full_path = os.path.normpath(candidate)
            if not _is_path_within_root(full_path, self.project_root):
                return None, None, "安全错误：不允许搜索项目目录外的内容"
            relative_path = _normalize_rel_path(
                os.path.relpath(full_path, self.project_root).replace("\\", "/")
            )
        else:
            relative_path = _normalize_rel_path(candidate)
            full_path = os.path.normpath(os.path.join(self.project_root, relative_path))
            if not _is_path_within_root(full_path, self.project_root):
                return None, None, "安全错误：不允许搜索项目目录外的内容"

        if not relative_path:
            return None, None, "必须提供 file_path"
        if _has_hidden_or_test_segment(relative_path):
            return None, None, f"文件被排除: {relative_path}"
        if not os.path.exists(full_path):
            return None, None, f"文件不存在: {relative_path}"
        if not os.path.isfile(full_path):
            return None, None, f"不是文件: {relative_path}"
        if self.target_files and relative_path not in self.target_files:
            return None, None, f"文件不在目标范围内: {relative_path}"

        filename = os.path.basename(relative_path)
        for excl_pattern in self.exclude_patterns:
            if fnmatch.fnmatch(relative_path, excl_pattern) or fnmatch.fnmatch(filename, excl_pattern):
                return None, None, f"文件被排除: {relative_path}"

        return relative_path, full_path, None

    @staticmethod
    def _looks_like_specific_file_pattern(patterns: List[str]) -> Optional[str]:
        if len(patterns) != 1:
            return None
        candidate = _normalize_rel_path(patterns[0])
        if not candidate:
            return None
        if "/" not in candidate:
            return None
        if any(meta in candidate for meta in ("*", "?", "[", "]")):
            return None
        return candidate

    def _build_rg_command(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
    ) -> List[str]:
        cmd = ["rg", "--line-number", "--column", "--no-heading", "--color", "never", "--max-columns", "300"]
        if not case_sensitive:
            cmd.append("-i")
        if not is_regex:
            cmd.append("-F")
        cmd.extend(["-e", keyword])
        for pattern in normalized_patterns:
            cmd.extend(["-g", pattern])
        for excluded_dir in sorted(self.exclude_dirs):
            cmd.extend(["-g", f"!{excluded_dir}/**"])
        for excl_pattern in self.exclude_patterns:
            if excl_pattern and not excl_pattern.startswith("!"):
                cmd.extend(["-g", f"!{excl_pattern}"])
        cmd.append(search_dir)
        return cmd

    def _search_with_rg_sync(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
        max_results: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        cmd = self._build_rg_command(
            keyword=keyword,
            search_dir=search_dir,
            normalized_patterns=normalized_patterns,
            case_sensitive=case_sensitive,
            is_regex=is_regex,
        )
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode not in (0, 1):
            stderr = str(proc.stderr or "").strip()
            raise RuntimeError(stderr or "rg 执行失败")

        results: List[Dict[str, Any]] = []
        seen_key: set[tuple[str, int]] = set()
        raw_match_count = 0
        stdout_text = str(proc.stdout or "")
        for raw_line in stdout_text.splitlines():
            parts = raw_line.split(":", 3)
            if len(parts) < 4:
                continue
            path_part, line_part, column_part, match_part = parts[0], parts[1], parts[2], parts[3]
            try:
                line_number = int(line_part)
            except Exception:
                continue
            try:
                column_number = int(column_part)
            except Exception:
                column_number = None

            full_path = os.path.normpath(path_part)
            if not _is_path_within_root(full_path, self.project_root):
                continue
            relative_path = _normalize_rel_path(
                os.path.relpath(full_path, self.project_root).replace("\\", "/")
            )
            filename = os.path.basename(relative_path)
            if self._should_skip_candidate(relative_path, filename):
                continue

            dedup_key = (relative_path, line_number)
            if dedup_key in seen_key:
                continue
            seen_key.add(dedup_key)
            raw_match_count += 1
            if len(results) < max_results:
                results.append(
                    {
                        "file": relative_path,
                        "line": line_number,
                        "column": column_number,
                        "match": str(match_part or "").strip()[:240],
                        "symbol_name": None,
                        "match_kind": "text",
                    }
                )

        return results, raw_match_count

    def _build_grep_command(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
    ) -> List[str]:
        cmd = ["grep", "-RIn", "--binary-files=without-match"]
        if not case_sensitive:
            cmd.append("-i")
        if not is_regex:
            cmd.append("-F")
        for excluded_dir in sorted(self.exclude_dirs):
            cmd.append(f"--exclude-dir={excluded_dir}")
        for pattern in normalized_patterns:
            cmd.append(f"--include={pattern}")
        for excl_pattern in self.exclude_patterns:
            if "/" not in excl_pattern:
                cmd.append(f"--exclude={excl_pattern}")
        cmd.extend([keyword, search_dir])
        return cmd

    def _search_with_grep_sync(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
        max_results: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        cmd = self._build_grep_command(
            keyword=keyword,
            search_dir=search_dir,
            normalized_patterns=normalized_patterns,
            case_sensitive=case_sensitive,
            is_regex=is_regex,
        )
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode not in (0, 1):
            stderr = str(proc.stderr or "").strip()
            raise RuntimeError(stderr or "grep 执行失败")

        results: List[Dict[str, Any]] = []
        seen_key: set[tuple[str, int]] = set()
        raw_match_count = 0
        for raw_line in str(proc.stdout or "").splitlines():
            parts = raw_line.split(":", 2)
            if len(parts) < 3:
                continue
            path_part, line_part, match_part = parts[0], parts[1], parts[2]
            try:
                line_number = int(line_part)
            except Exception:
                continue
            full_path = os.path.normpath(path_part)
            if not _is_path_within_root(full_path, self.project_root):
                continue
            relative_path = _normalize_rel_path(
                os.path.relpath(full_path, self.project_root).replace("\\", "/")
            )
            filename = os.path.basename(relative_path)
            if self._should_skip_candidate(relative_path, filename):
                continue
            dedup_key = (relative_path, line_number)
            if dedup_key in seen_key:
                continue
            seen_key.add(dedup_key)
            raw_match_count += 1
            if len(results) < max_results:
                results.append(
                    {
                        "file": relative_path,
                        "line": line_number,
                        "column": None,
                        "match": str(match_part or "").strip()[:240],
                        "symbol_name": None,
                        "match_kind": "text",
                    }
                )

        return results, raw_match_count

    def _search_with_python_sync(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
        max_results: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(keyword if is_regex else re.escape(keyword), flags)
        results: List[Dict[str, Any]] = []
        raw_match_count = 0

        for root, dirs, files in os.walk(search_dir):
            rel_dir = os.path.relpath(root, self.project_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d
                for d in dirs
                if d not in self.exclude_dirs
                and not d.startswith(".")
                and not _has_hidden_or_test_segment(f"{rel_dir}/{d}" if rel_dir else d)
            ]
            for filename in files:
                if normalized_patterns and not any(
                    fnmatch.fnmatch(filename, item) for item in normalized_patterns
                ):
                    continue
                file_path = os.path.join(root, filename)
                relative_path = _normalize_rel_path(
                    os.path.relpath(file_path, self.project_root).replace("\\", "/")
                )
                if self._should_skip_candidate(relative_path, filename):
                    continue
                try:
                    lines = self._read_file_lines_sync(file_path)
                except Exception:
                    continue
                for idx, line in enumerate(lines, start=1):
                    if not pattern.search(line):
                        continue
                    raw_match_count += 1
                    if len(results) < max_results:
                        results.append(
                            {
                                "file": relative_path,
                                "line": idx,
                                "column": None,
                                "match": line.strip()[:240],
                                "symbol_name": None,
                                "match_kind": "text",
                            }
                        )
        return results, raw_match_count

    def _run_search_engines_sync(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
        max_results: int,
    ) -> tuple[List[Dict[str, Any]], int, str]:
        if shutil.which("rg"):
            try:
                results, files_searched = self._search_with_rg_sync(
                    keyword=keyword,
                    search_dir=search_dir,
                    normalized_patterns=normalized_patterns,
                    case_sensitive=case_sensitive,
                    is_regex=is_regex,
                    max_results=max_results,
                )
                return results, files_searched, "rg"
            except Exception:
                pass

        if shutil.which("grep"):
            try:
                results, files_searched = self._search_with_grep_sync(
                    keyword=keyword,
                    search_dir=search_dir,
                    normalized_patterns=normalized_patterns,
                    case_sensitive=case_sensitive,
                    is_regex=is_regex,
                    max_results=max_results,
                )
                return results, files_searched, "grep"
            except Exception:
                pass

        results, files_searched = self._search_with_python_sync(
            keyword=keyword,
            search_dir=search_dir,
            normalized_patterns=normalized_patterns,
            case_sensitive=case_sensitive,
            is_regex=is_regex,
            max_results=max_results,
        )
        return results, files_searched, "python"

    @property
    def name(self) -> str:
        return "search_code"
    
    @property
    def description(self) -> str:
        return """在项目代码中搜索关键字或模式。

使用场景:
- 查找特定函数的所有调用位置
- 搜索特定的 API 使用
- 查找包含特定模式的代码

输入:
- keyword: 搜索关键字或正则表达式
- file_pattern: 可选，文件名模式（如 *.py）
- directory: 可选，搜索目录 (相对于项目根目录)
- case_sensitive: 是否区分大小写（默认 false）
- is_regex: 是否使用正则表达式（默认 false）
- max_results: 最大返回结果数（默认10，最多10）

注意:
- test / tests 目录默认被排除在搜索范围之外
- 若指定的 directory 中无结果，会自动回退到整个项目根目录重新搜索

这是一个纯定位工具，只返回命中位置和摘要，不返回上下文窗口。"""
    
    @property
    def args_schema(self):
        return FileSearchInput
    
    async def _execute(
        self,
        keyword: str,
        file_path: Optional[str] = None,
        path: Optional[str] = None,
        file_pattern: Optional[str] = None,
        directory: Optional[str] = None,
        case_sensitive: bool = False,
        max_results: int = 50,
        is_regex: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            normalized_patterns = _split_file_patterns(file_pattern)
            requested_single_file = str(file_path or path or "").strip()
            if not requested_single_file:
                inferred = self._looks_like_specific_file_pattern(normalized_patterns)
                if inferred:
                    requested_single_file = inferred

            single_file_mode = False
            single_file_rel: Optional[str] = None
            single_file_abs: Optional[str] = None
            if requested_single_file:
                single_file_rel, single_file_abs, file_error = self._resolve_single_file_target(
                    requested_single_file
                )
                if file_error or not single_file_rel or not single_file_abs:
                    return ToolResult(success=False, error=file_error or "文件定位失败")
                search_dir_rel, search_dir_abs, dir_error = self._normalize_directory(
                    os.path.dirname(single_file_rel) or "."
                )
                normalized_patterns = [os.path.basename(single_file_rel)]
                single_file_mode = True
            else:
                search_dir_rel, search_dir_abs, dir_error = self._normalize_directory(directory)

            if dir_error or not search_dir_abs or not search_dir_rel:
                return ToolResult(success=False, error=dir_error or "搜索目录解析失败")

            # Auto-detect regex: if keyword contains regex metacharacters (|, (, ), [, ]), treat as regex
            _REGEX_META_RE = re.compile(r'[|()\[\]{}+?^$\\]')
            if not is_regex and _REGEX_META_RE.search(keyword):
                try:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    re.compile(keyword, flags)
                    is_regex = True
                except re.error:
                    pass  # Not valid regex, keep is_regex=False and search literally

            if is_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    re.compile(keyword, flags)
                except re.error as exc:
                    return ToolResult(success=False, error=f"无效的搜索模式: {exc}")

            safe_max_results = max(1, min(int(max_results or 10), 10))
            results, raw_match_count, engine = await asyncio.to_thread(
                self._run_search_engines_sync,
                keyword,
                search_dir_abs,
                normalized_patterns,
                case_sensitive,
                is_regex,
                safe_max_results,
            )

            scope_fallback_applied = False
            effective_directory = search_dir_rel
            if not single_file_mode and not results and search_dir_rel not in {"", "."}:
                fallback_results, fallback_raw_match_count, fallback_engine = await asyncio.to_thread(
                    self._run_search_engines_sync,
                    keyword,
                    self.project_root,
                    normalized_patterns,
                    case_sensitive,
                    is_regex,
                    safe_max_results,
                )
                if fallback_results:
                    scope_fallback_applied = True
                    effective_directory = "."
                    results = fallback_results
                    raw_match_count = fallback_raw_match_count
                    engine = fallback_engine

            if not results:
                command_chain = _unique_command_chain([engine])
                display_command = _build_display_command(command_chain)
                entries: List[Dict[str, Any]] = []
                _validate_evidence_metadata(
                    render_type="search_hits",
                    command_chain=command_chain,
                    display_command=display_command,
                    entries=entries,
                )
                return ToolResult(
                    success=True,
                    data=(
                        f"没有找到匹配 '{keyword}' 的内容\n"
                        f"搜索目录: {effective_directory}\n"
                        f"执行引擎: {engine}\n"
                        f"原始命中数: 0"
                    ),
                    metadata={
                        "keyword": keyword,
                        "match_count_raw": 0,
                        "match_count_returned": 0,
                        "overflow_count": 0,
                        "normalized_file_patterns": normalized_patterns,
                        "engine": engine,
                        "render_type": "search_hits",
                        "command_chain": command_chain,
                        "display_command": display_command,
                        "entries": entries,
                        "recommended_followup_tool": "list_files",
                        "scope_fallback_applied": scope_fallback_applied,
                        "original_directory": search_dir_rel,
                        "effective_directory": effective_directory,
                        "single_file_mode": single_file_mode,
                        "target_file": single_file_rel,
                    },
                )

            entries: List[Dict[str, Any]] = []
            aggregate_command_chain: List[str] = [engine]
            for item in results:
                entries.append(
                    {
                        "file_path": item["file"],
                        "line": int(item["line"]),
                        "match_line": int(item["line"]),
                        "column": item.get("column"),
                        "match_text": str(item["match"]),
                        "symbol_name": item.get("symbol_name"),
                        "match_kind": item.get("match_kind") or "text",
                    }
                )

            aggregate_command_chain = _unique_command_chain(aggregate_command_chain)
            display_command = _build_display_command(aggregate_command_chain)
            _validate_evidence_metadata(
                render_type="search_hits",
                command_chain=aggregate_command_chain,
                display_command=display_command,
                entries=entries,
            )

            output_parts = [
                f"搜索关键字: '{keyword}'",
                f"原始命中数: {raw_match_count}",
                f"返回结果数: {len(entries)}",
                f"执行链路: {display_command}",
            ]
            for entry in entries:
                location = f"{entry['file_path']}:{entry['match_line']}"
                if entry.get("column"):
                    location += f":{entry['column']}"
                output_parts.append(f"- {location} {entry['match_text']}")
            if raw_match_count > safe_max_results:
                output_parts.append(
                    "\n命中过多，请继续通过 directory、file_pattern 或更精确的 regex 收敛搜索。"
                )

            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "keyword": keyword,
                    "match_count_raw": raw_match_count,
                    "match_count_returned": len(entries),
                    "overflow_count": max(0, raw_match_count - len(entries)),
                    "normalized_file_patterns": normalized_patterns,
                    "results": [
                        {
                            "file": entry["file_path"],
                            "line": entry["match_line"],
                            "match": entry["match_text"],
                            "column": entry.get("column"),
                        }
                        for entry in entries[:10]
                    ],
                    "engine": engine,
                    "render_type": "search_hits",
                    "command_chain": aggregate_command_chain,
                    "display_command": display_command,
                    "entries": entries,
                    "recommended_followup_tool": (
                        "search_code" if raw_match_count > safe_max_results else "get_code_window"
                    ),
                    "scope_fallback_applied": scope_fallback_applied,
                    "original_directory": search_dir_rel,
                    "effective_directory": effective_directory,
                    "single_file_mode": single_file_mode,
                    "target_file": single_file_rel,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {str(e)}")


class CodeWindowInput(BaseModel):
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    anchor_line: int = Field(description="锚点行号（从1开始）")
    before_lines: int = Field(default=2, description="向前读取的行数")
    after_lines: int = Field(default=2, description="向后读取的行数")


class CodeWindowTool(AgentTool):
    def __init__(
        self,
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )

    @property
    def name(self) -> str:
        return "get_code_window"

    @property
    def description(self) -> str:
        return "围绕 file_path + anchor_line 返回极小代码窗口，用于取证和前端代码展示。"

    @property
    def args_schema(self):
        return CodeWindowInput

    async def _execute(
        self,
        file_path: str,
        anchor_line: int,
        before_lines: int = 2,
        after_lines: int = 2,
        **kwargs,
    ) -> ToolResult:
        try:
            relative_path, full_path, error = _resolve_project_file(
                project_root=self.project_root,
                file_path=file_path,
                target_files=self.target_files,
            )
            if error or not relative_path or not full_path:
                return ToolResult(success=False, error=error or "文件定位失败")

            focus_line = max(1, int(anchor_line or 1))
            before = max(0, min(int(before_lines or 0), 20))
            after = max(0, min(int(after_lines or 0), 20))
            if before + after > 40:
                return ToolResult(success=False, error="代码窗口跨度过大，请缩小 before_lines/after_lines")

            lines = await asyncio.to_thread(_read_lines_sync, full_path)
            if not lines:
                return ToolResult(success=False, error=f"文件为空: {relative_path}")
            if focus_line > len(lines):
                return ToolResult(success=False, error=f"锚点行超出文件范围: {relative_path}:{focus_line}")

            start_line = max(1, focus_line - before)
            end_line = min(len(lines), focus_line + after)
            selected = [lines[index - 1].rstrip("\n") for index in range(start_line, end_line + 1)]
            language = _detect_language(relative_path)
            structured_lines = _build_structured_lines(
                selected_lines=selected,
                start_line=start_line,
                focus_start_line=focus_line,
                focus_end_line=focus_line,
                focus_kind="focus",
            )
            command_chain = ["get_code_window"]
            display_command = _build_display_command(command_chain)
            entries = [
                {
                    "file_path": relative_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "focus_line": focus_line,
                    "language": language,
                    "lines": structured_lines,
                }
            ]
            _validate_evidence_metadata(
                render_type="code_window",
                command_chain=command_chain,
                display_command=display_command,
                entries=entries,
            )
            return ToolResult(
                success=True,
                data=(
                    f"文件: {relative_path}\n"
                    f"窗口: {start_line}-{end_line}\n\n"
                    f"```{language}\n{_format_structured_lines_for_code_block(structured_lines)}\n```"
                ),
                metadata={
                    "file_path": relative_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "focus_line": focus_line,
                    "language": language,
                    "render_type": "code_window",
                    "command_chain": command_chain,
                    "display_command": display_command,
                    "entries": entries,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"获取代码窗口失败: {exc}")


class FileOutlineInput(BaseModel):
    file_path: str = Field(description="文件路径（相对于项目根目录）")


class FileOutlineTool(AgentTool):
    def __init__(
        self,
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )

    @property
    def name(self) -> str:
        return "get_file_outline"

    @property
    def description(self) -> str:
        return "返回文件职责、关键符号、imports、入口点和风险提示，不输出大段源码。"

    @property
    def args_schema(self):
        return FileOutlineInput

    async def _execute(self, file_path: str, **kwargs) -> ToolResult:
        try:
            relative_path, full_path, error = _resolve_project_file(
                project_root=self.project_root,
                file_path=file_path,
                target_files=self.target_files,
            )
            if error or not relative_path or not full_path:
                return ToolResult(success=False, error=error or "文件定位失败")

            content = await asyncio.to_thread(_read_text_sync, full_path)
            imports = []
            for pattern in (
                r"^\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)$",
                r"^\s*(?:#include\s+[<\"].+[>\"]|use\s+.+;|import\s+.+;)$",
            ):
                for match in re.finditer(pattern, content, re.MULTILINE):
                    candidate = str(match.group(0) or "").strip()
                    if candidate and candidate not in imports:
                        imports.append(candidate)
                    if len(imports) >= 12:
                        break
                if len(imports) >= 12:
                    break

            key_symbols = _extract_related_symbols(content, limit=12)
            framework_hints = _infer_framework_hints(content, relative_path)
            risk_markers = _extract_risk_markers(content)
            entrypoints = [
                symbol
                for symbol in key_symbols
                if any(token in symbol.lower() for token in ("main", "handler", "route", "index", "app", "run"))
            ][:6]
            file_role = "implementation"
            lowered_path = relative_path.lower()
            if any(token in lowered_path for token in ("route", "controller", "handler", "api")):
                file_role = "entrypoint"
            elif any(token in lowered_path for token in ("util", "helper", "service")):
                file_role = "supporting_module"
            elif lowered_path.endswith((".yml", ".yaml", ".json", ".toml", ".ini")):
                file_role = "configuration"

            entry = {
                "file_path": relative_path,
                "file_role": file_role,
                "key_symbols": key_symbols,
                "imports": imports,
                "entrypoints": entrypoints,
                "risk_markers": risk_markers,
                "framework_hints": framework_hints,
            }
            command_chain = ["get_file_outline"]
            display_command = _build_display_command(command_chain)
            _validate_evidence_metadata(
                render_type="outline_summary",
                command_chain=command_chain,
                display_command=display_command,
                entries=[entry],
            )
            return ToolResult(
                success=True,
                data="\n".join(
                    [
                        f"文件: {relative_path}",
                        f"角色: {file_role}",
                        f"关键符号: {', '.join(key_symbols) if key_symbols else '无'}",
                        f"入口点: {', '.join(entrypoints) if entrypoints else '无'}",
                        f"风险标记: {', '.join(risk_markers) if risk_markers else '无'}",
                        f"框架提示: {', '.join(framework_hints) if framework_hints else '无'}",
                    ]
                ),
                metadata={
                    "render_type": "outline_summary",
                    "command_chain": command_chain,
                    "display_command": display_command,
                    "entries": [entry],
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"获取文件概览失败: {exc}")


class FunctionSummaryInput(BaseModel):
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    function_name: Optional[str] = Field(default=None, description="目标函数名")
    line: Optional[int] = Field(default=None, description="函数内任意锚点行")


class FunctionSummaryTool(AgentTool):
    def __init__(
        self,
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )
        self.locator = EnclosingFunctionLocator(project_root=project_root)

    @property
    def name(self) -> str:
        return "get_function_summary"

    @property
    def description(self) -> str:
        return "解释单个函数的职责、输入输出、关键调用与风险点，不返回大段源码。"

    @property
    def args_schema(self):
        return FunctionSummaryInput

    async def _execute(
        self,
        file_path: str,
        function_name: Optional[str] = None,
        line: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        try:
            relative_path, full_path, error = _resolve_project_file(
                project_root=self.project_root,
                file_path=file_path,
                target_files=self.target_files,
            )
            if error or not relative_path or not full_path:
                return ToolResult(success=False, error=error or "文件定位失败")

            resolved_function = str(function_name or "").strip()
            if not resolved_function and line is not None:
                located = self.locator.locate(
                    full_file_path=full_path,
                    line_start=max(1, int(line)),
                    relative_file_path=relative_path,
                )
                resolved_function = str(located.get("function") or "").strip()

            if not resolved_function:
                return ToolResult(success=False, error="必须提供 function_name 或有效 line 来定位函数")

            from .run_code import ExtractFunctionTool

            extractor = ExtractFunctionTool(project_root=self.project_root)
            extracted = await extractor.execute(path=relative_path, symbol_name=resolved_function)
            if not extracted.success:
                return ToolResult(success=False, error=extracted.error or f"无法定位函数: {resolved_function}")

            metadata = extracted.metadata or {}
            code = str(metadata.get("code") or "")
            signature = code.splitlines()[0].strip() if code else resolved_function
            inputs = list(metadata.get("parameters") or [])
            key_calls = _extract_key_calls(code)
            risk_points = _extract_risk_markers(code)
            outputs = []
            if re.search(r"\breturn\b", code):
                outputs.append("returns_value")
            if risk_points:
                outputs.append("side_effects")
            if not outputs:
                outputs.append("unknown")
            purpose = f"处理 `{resolved_function}` 的核心逻辑"
            if key_calls:
                purpose += f"，重点依赖 {', '.join(key_calls[:3])}"

            entry = {
                "file_path": relative_path,
                "resolved_function": resolved_function,
                "signature": signature,
                "purpose": purpose,
                "inputs": inputs,
                "outputs": outputs,
                "key_calls": key_calls,
                "risk_points": risk_points,
                "related_symbols": _extract_related_symbols(code),
            }
            command_chain = ["get_function_summary"]
            display_command = _build_display_command(command_chain)
            _validate_evidence_metadata(
                render_type="function_summary",
                command_chain=command_chain,
                display_command=display_command,
                entries=[entry],
            )
            return ToolResult(
                success=True,
                data="\n".join(
                    [
                        f"文件: {relative_path}",
                        f"函数: {resolved_function}",
                        f"签名: {signature}",
                        f"职责: {purpose}",
                        f"输入: {', '.join(inputs) if inputs else '未识别'}",
                        f"输出: {', '.join(outputs) if outputs else '未识别'}",
                        f"关键调用: {', '.join(key_calls) if key_calls else '无'}",
                        f"风险点: {', '.join(risk_points) if risk_points else '无'}",
                    ]
                ),
                metadata={
                    "render_type": "function_summary",
                    "command_chain": command_chain,
                    "display_command": display_command,
                    "entries": [entry],
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"获取函数摘要失败: {exc}")


class SymbolBodyInput(BaseModel):
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    symbol_name: str = Field(description="目标符号名")


class SymbolBodyTool(AgentTool):
    def __init__(
        self,
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )

    @property
    def name(self) -> str:
        return "get_symbol_body"

    @property
    def description(self) -> str:
        return "提取函数/方法主体源码，只负责源码提取，不负责语义解释。"

    @property
    def args_schema(self):
        return SymbolBodyInput

    async def _execute(self, file_path: str, symbol_name: str, **kwargs) -> ToolResult:
        try:
            relative_path, full_path, error = _resolve_project_file(
                project_root=self.project_root,
                file_path=file_path,
                target_files=self.target_files,
            )
            if error or not relative_path or not full_path:
                return ToolResult(success=False, error=error or "文件定位失败")

            from .run_code import ExtractFunctionTool

            extractor = ExtractFunctionTool(project_root=self.project_root)
            extracted = await extractor.execute(path=relative_path, symbol_name=symbol_name)
            if not extracted.success:
                return ToolResult(success=False, error=extracted.error or f"无法提取符号: {symbol_name}")

            payload = extracted.metadata or {}
            body = str(payload.get("code") or "")
            start_line = int(payload.get("line_start") or 1)
            end_line = int(payload.get("line_end") or start_line)
            language = _detect_language(relative_path)
            structured_lines = _build_structured_lines(
                body.splitlines(),
                start_line,
                start_line,
                start_line,
                "focus",
            )
            entry = {
                "file_path": relative_path,
                "symbol_name": symbol_name,
                "start_line": start_line,
                "end_line": end_line,
                "body": body,
                "language": language,
                "lines": structured_lines,
            }
            command_chain = ["get_symbol_body"]
            display_command = _build_display_command(command_chain)
            _validate_evidence_metadata(
                render_type="symbol_body",
                command_chain=command_chain,
                display_command=display_command,
                entries=[entry],
            )
            return ToolResult(
                success=True,
                data=(
                    f"符号: {symbol_name}\n"
                    f"文件: {relative_path}\n"
                    f"范围: {start_line}-{end_line}\n\n"
                    f"```{language}\n{body}\n```"
                ),
                metadata={
                    "render_type": "symbol_body",
                    "command_chain": command_chain,
                    "display_command": display_command,
                    "entries": [entry],
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"提取符号源码失败: {exc}")


class ListFilesInput(BaseModel):
    """列出文件输入"""
    directory: str = Field(default=".", description="目录路径（相对于项目根目录）")
    pattern: Optional[str] = Field(default=None, description="文件名模式，如 *.py")
    recursive: bool = Field(default=False, description="是否递归列出子目录")
    max_files: int = Field(default=100, description="最大文件数")
    recursive_mode: Optional[str] = Field(default=None, description="shallow/deep，兼容更明确的递归模式")
    max_entries: Optional[int] = Field(default=None, description="最大返回条目数")


class ListFilesTool(AgentTool):
    """
    列出文件工具
    列出目录中的文件
    """
    
    DEFAULT_EXCLUDE_DIRS = {
        "node_modules", "vendor", "dist", "build", ".git",
        "__pycache__", ".pytest_cache", "coverage", "test", "tests",
    }
    
    def __init__(
        self, 
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )
        
        # 从 exclude_patterns 中提取目录排除
        self.exclude_dirs = set(self.DEFAULT_EXCLUDE_DIRS)
        for pattern in self.exclude_patterns:
            # 如果是目录模式（如 node_modules/**），提取目录名
            if pattern.endswith("/**"):
                self.exclude_dirs.add(pattern[:-3])
            elif "/" not in pattern and "*" not in pattern:
                self.exclude_dirs.add(pattern)
    
    @property
    def name(self) -> str:
        return "list_files"
    
    @property
    def description(self) -> str:
        return """列出目录中的文件。

使用场景:
- 了解项目结构
- 查找特定类型的文件
- 浏览目录内容

输入:
- directory: 目录路径 (相对于项目根目录)
- pattern: 可选，文件名模式
- recursive: 是否递归
- max_files: 最大文件数"""
    
    @property
    def args_schema(self):
        return ListFilesInput

    def _repair_directory_hint(self, directory: str) -> Optional[str]:
        wanted = _normalize_rel_path(directory)
        if not wanted or wanted == ".":
            return None
        basename = os.path.basename(wanted)
        matches: List[str] = []
        for root, dirnames, _files in os.walk(self.project_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for dirname in dirnames:
                candidate = _normalize_rel_path(
                    os.path.relpath(os.path.join(root, dirname), self.project_root).replace("\\", "/")
                )
                if candidate == wanted or os.path.basename(candidate) == basename:
                    matches.append(candidate)
                    if len(matches) > 1:
                        return None
        return matches[0] if len(matches) == 1 else None

    async def _execute(
        self,
        directory: str = ".",
        pattern: Optional[str] = None,
        recursive: bool = False,
        max_files: int = 100,
        recursive_mode: Optional[str] = None,
        max_entries: Optional[int] = None,
        **kwargs
    ) -> ToolResult:
        """执行文件列表"""
        try:
            # 🔥 兼容性处理：支持 path 参数作为 directory 的别名
            if "path" in kwargs and kwargs["path"]:
                directory = kwargs["path"]

            if recursive_mode:
                recursive = str(recursive_mode).strip().lower() in {"deep", "recursive", "true", "1"}
            if max_entries is not None:
                max_files = int(max_entries)
            max_files = max(1, min(int(max_files or 100), 200))

            target_dir = os.path.normpath(os.path.join(self.project_root, directory))
            if not target_dir.startswith(os.path.normpath(self.project_root)):
                return ToolResult(
                    success=False,
                    error="安全错误：不允许访问项目目录外的目录",
                )

            if not os.path.exists(target_dir):
                repaired = self._repair_directory_hint(directory)
                if repaired:
                    directory = repaired
                    target_dir = os.path.normpath(os.path.join(self.project_root, repaired))
                else:
                    return ToolResult(
                        success=False,
                        error=f"目录不存在: {directory}",
                    )

            if not os.path.exists(target_dir):
                return ToolResult(
                    success=False,
                    error=f"目录不存在: {directory}",
                )
            
            files = []
            dirs = []
            
            if recursive:
                for root, dirnames, filenames in os.walk(target_dir):
                    # 排除目录
                    rel_dir = os.path.relpath(root, self.project_root).replace("\\", "/")
                    if rel_dir == ".":
                        rel_dir = ""
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if d not in self.exclude_dirs
                        and not d.startswith(".")
                        and not _has_hidden_or_test_segment(f"{rel_dir}/{d}" if rel_dir else d)
                    ]
                    
                    for filename in filenames:
                        if pattern and not fnmatch.fnmatch(filename, pattern):
                            continue
                        
                        full_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(full_path, self.project_root)
                        relative_path = _normalize_rel_path(relative_path)
                        if _has_hidden_or_test_segment(relative_path):
                            continue
                        
                        # 检查是否在目标文件列表中
                        if self.target_files and relative_path not in self.target_files:
                            continue
                        
                        # 检查排除模式
                        should_skip = False
                        for excl_pattern in self.exclude_patterns:
                            if fnmatch.fnmatch(relative_path, excl_pattern) or fnmatch.fnmatch(filename, excl_pattern):
                                should_skip = True
                                break
                        if should_skip:
                            continue
                        
                        files.append(relative_path)
                        
                        if len(files) >= max_files:
                            break
                    
                    if len(files) >= max_files:
                        break
            else:
                # 🔥 如果设置了 target_files，只显示目标文件和包含目标文件的目录
                if self.target_files:
                    # 计算哪些目录包含目标文件
                    dirs_with_targets = set()
                    for tf in self.target_files:
                        # 获取目标文件的目录部分
                        tf_dir = os.path.dirname(tf)
                        while tf_dir:
                            dirs_with_targets.add(tf_dir)
                            tf_dir = os.path.dirname(tf_dir)
                    
                    for item in os.listdir(target_dir):
                        if item in self.exclude_dirs:
                            continue
                        if item.startswith("."):
                            continue
                        
                        full_path = os.path.join(target_dir, item)
                        relative_path = os.path.relpath(full_path, self.project_root)
                        relative_path = _normalize_rel_path(relative_path)
                        if _has_hidden_or_test_segment(relative_path):
                            continue
                        
                        if os.path.isdir(full_path):
                            # 只显示包含目标文件的目录
                            if relative_path in dirs_with_targets or any(
                                tf.startswith(relative_path + "/") for tf in self.target_files
                            ):
                                dirs.append(relative_path + "/")
                        else:
                            if pattern and not fnmatch.fnmatch(item, pattern):
                                continue
                            
                            # 检查是否在目标文件列表中
                            if relative_path not in self.target_files:
                                continue
                            
                            files.append(relative_path)
                            
                            if len(files) >= max_files:
                                break
                else:
                    # 没有设置 target_files，正常列出
                    for item in os.listdir(target_dir):
                        if item in self.exclude_dirs:
                            continue
                        if item.startswith("."):
                            continue
                        
                        full_path = os.path.join(target_dir, item)
                        relative_path = os.path.relpath(full_path, self.project_root)
                        relative_path = _normalize_rel_path(relative_path)
                        if _has_hidden_or_test_segment(relative_path):
                            continue
                        
                        if os.path.isdir(full_path):
                            dirs.append(relative_path + "/")
                        else:
                            if pattern and not fnmatch.fnmatch(item, pattern):
                                continue
                            
                            # 检查排除模式
                            should_skip = False
                            for excl_pattern in self.exclude_patterns:
                                if fnmatch.fnmatch(relative_path, excl_pattern) or fnmatch.fnmatch(item, excl_pattern):
                                    should_skip = True
                                    break
                            if should_skip:
                                continue
                            
                            files.append(relative_path)
                            
                            if len(files) >= max_files:
                                break
            
            # 格式化输出
            output_parts = [f"📁 目录: {directory}\n"]
            
            # 🔥 如果设置了 target_files，显示提示信息
            if self.target_files:
                output_parts.append(f"注意: 审计范围限定为 {len(self.target_files)} 个指定文件\n")
            
            if dirs:
                output_parts.append("目录:")
                for d in sorted(dirs)[:20]:
                    output_parts.append(f"  📂 {d}")
                if len(dirs) > 20:
                    output_parts.append(f"  ... 还有 {len(dirs) - 20} 个目录")
            
            if files:
                output_parts.append(f"\n文件 ({len(files)}):")
                for f in sorted(files):
                    output_parts.append(f"  {f}")
            elif self.target_files:
                # 如果没有文件但设置了 target_files，显示目标文件列表
                output_parts.append(f"\n指定的目标文件 ({len(self.target_files)}):")
                for f in sorted(self.target_files)[:20]:
                    output_parts.append(f"  {f}")
                if len(self.target_files) > 20:
                    output_parts.append(f"  ... 还有 {len(self.target_files) - 20} 个文件")
            
            if len(files) >= max_files:
                output_parts.append(f"\n... 结果已截断（最大 {max_files} 个文件）")
            
            recommended_next_directories = sorted(dirs)[:5]
            truncated = len(files) >= max_files

            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "directory": directory,
                    "directories": sorted(dirs),
                    "files": sorted(files),
                    "file_count": len(files),
                    "dir_count": len(dirs),
                    "truncated": truncated,
                    "recommended_next_directories": recommended_next_directories,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"列出文件失败: {str(e)}",
            )


class LocateEnclosingFunctionInput(BaseModel):
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    line: int = Field(description="目标行号（从1开始）")

    @model_validator(mode="after")
    def validate_path_fields(self) -> "LocateEnclosingFunctionInput":
        if not str(self.file_path or "").strip():
            raise ValueError("必须提供 file_path")
        if int(self.line) <= 0:
            raise ValueError("line 必须为正整数")
        return self


def _extract_signature_lines(
    file_lines: List[str],
    *,
    start_line: Optional[int],
    language: Optional[str],
) -> str:
    if not start_line or start_line <= 0:
        return ""
    start_index = max(0, int(start_line) - 1)
    collected: List[str] = []
    max_lines = min(len(file_lines), start_index + 8)
    normalized_language = str(language or "").strip().lower()
    for idx in range(start_index, max_lines):
        line = file_lines[idx].strip()
        if not line:
            if collected:
                break
            continue
        collected.append(line)
        joined = " ".join(collected).strip()
        if normalized_language == "python" and joined.endswith(":"):
            return joined
        if normalized_language in {"c", "cpp", "javascript", "typescript", "tsx", "java", "kotlin"} and "{" in joined:
            return joined.split("{", 1)[0].strip()
    return " ".join(collected).strip()


def _split_signature_parameters(signature: str) -> str:
    match = re.search(r"\((.*)\)", str(signature or "").strip())
    return str(match.group(1) or "").strip() if match else ""


def _split_top_level_commas(raw: str) -> List[str]:
    if not raw:
        return []
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    for char in raw:
        if char in "(<[":
            depth += 1
        elif char in ")>]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            segment = "".join(current).strip()
            if segment:
                parts.append(segment)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_python_parameters(signature: str) -> List[Dict[str, Any]]:
    raw_params = _split_top_level_commas(_split_signature_parameters(signature))
    parameters: List[Dict[str, Any]] = []
    for position, raw_param in enumerate(raw_params):
        cleaned = str(raw_param or "").strip()
        if not cleaned or cleaned in {"/", "*"}:
            continue
        default = None
        required = True
        if "=" in cleaned:
            left, right = cleaned.split("=", 1)
            cleaned = left.strip()
            default = right.strip() or None
            required = False
        param_type = None
        if ":" in cleaned:
            name_part, type_part = cleaned.split(":", 1)
            name = name_part.strip()
            param_type = type_part.strip() or None
        else:
            name = cleaned
        parameters.append(
            {
                "name": name,
                "type": param_type,
                "default": default,
                "required": required,
                "position": position,
            }
        )
    return parameters


def _parse_c_like_parameter(raw_param: str, position: int) -> Dict[str, Any]:
    cleaned = str(raw_param or "").strip()
    if not cleaned:
        return {
            "name": "",
            "type": None,
            "default": None,
            "required": True,
            "position": position,
        }
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned == "void":
        return {
            "name": "void",
            "type": None,
            "default": None,
            "required": False,
            "position": position,
        }
    match = re.match(r"^(?P<type>.+?[\s\*&])(?P<name>[A-Za-z_][A-Za-z0-9_]*)$", cleaned)
    if match:
        param_type = str(match.group("type") or "").strip()
        name = str(match.group("name") or "").strip()
    else:
        parts = cleaned.rsplit(" ", 1)
        if len(parts) == 2:
            param_type, name = parts[0].strip(), parts[1].strip()
            while name.startswith(("*", "&")):
                param_type = f"{param_type} {name[0]}".strip()
                name = name[1:].strip()
        else:
            param_type, name = None, cleaned
    return {
        "name": name,
        "type": param_type or None,
        "default": None,
        "required": True,
        "position": position,
    }


def _extract_symbol_signature(
    *,
    signature: str,
    function_name: str,
    language: Optional[str],
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    normalized_language = str(language or "").strip().lower()
    if normalized_language == "python":
        return_type = None
        match = re.search(r"\)\s*->\s*([^:]+):?$", signature)
        if match:
            return_type = str(match.group(1) or "").strip() or None
        return _parse_python_parameters(signature), return_type

    raw_params = _split_top_level_commas(_split_signature_parameters(signature))
    parameters = []
    for position, raw_param in enumerate(raw_params):
        parsed = _parse_c_like_parameter(raw_param, position)
        if parsed["name"] == "void" and len(raw_params) == 1:
            return [], None
        parameters.append(parsed)

    prefix_match = re.match(
        rf"^(?P<prefix>.+?)\b{re.escape(function_name)}\s*\(",
        signature,
    )
    return_type = str(prefix_match.group("prefix") or "").strip() or None if prefix_match else None
    return parameters, return_type


class LocateEnclosingFunctionTool(AgentTool):
    def __init__(
        self,
        project_root: str,
        exclude_patterns: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or []
        self.target_files = set(target_files) if target_files else None
        self.locator = EnclosingFunctionLocator(project_root=project_root)

    @property
    def name(self) -> str:
        return "locate_enclosing_function"

    @property
    def description(self) -> str:
        return "根据 file_path + line 定位包含该行的函数/方法，并返回符号范围与签名事实。"

    @property
    def args_schema(self):
        return LocateEnclosingFunctionInput

    def _resolve_full_path(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        normalized = _normalize_rel_path(file_path)
        if not normalized:
            return None, "必须提供 file_path"
        full_path = os.path.normpath(os.path.join(self.project_root, normalized))
        root_path = os.path.normpath(self.project_root)
        if not _is_path_within_root(full_path, root_path):
            return None, "安全错误：不允许读取项目目录外的内容"
        if self.target_files and normalized not in self.target_files:
            return None, f"文件不在审计范围内: {normalized}"
        if not os.path.exists(full_path):
            return None, f"文件不存在: {normalized}"
        if not os.path.isfile(full_path):
            return None, f"不是文件: {normalized}"
        return full_path, None

    async def _execute(
        self,
        file_path: str,
        line: int,
    ) -> ToolResult:
        effective_path = str(file_path or "").strip()
        normalized_line = max(1, int(line))

        full_path, error = self._resolve_full_path(effective_path)
        if full_path is None:
            error_text = error or "文件定位失败"
            error_code = "path_out_of_scope" if "项目目录外" in error_text or "审计范围" in error_text else "not_found"
            return ToolResult(success=False, error=error_text, error_code=error_code)

        relative_path = _normalize_rel_path(effective_path)
        file_lines = await asyncio.to_thread(_read_lines_sync, full_path)
        total_lines = len(file_lines)
        if total_lines <= 0:
            return ToolResult(success=False, error=f"文件为空: {relative_path}", error_code="not_found")
        if normalized_line > total_lines:
            return ToolResult(
                success=False,
                error=f"目标行号超出文件范围: {relative_path}:{normalized_line}",
                error_code="invalid_input",
            )

        located = self.locator.locate(
            full_file_path=full_path,
            line_start=normalized_line,
            relative_file_path=relative_path,
            file_lines=file_lines,
        )
        resolution_engine = str(located.get("resolution_engine") or "missing_enclosing_function")
        resolution_method = str(located.get("resolution_method") or "missing_enclosing_function")
        language = located.get("language")
        diagnostics = list(located.get("diagnostics") or [])
        if resolution_engine in {"unsupported_language", "language_disabled"}:
            return ToolResult(
                success=False,
                error=f"暂不支持定位该语言的包围函数: {relative_path}",
                error_code="unsupported_language",
                diagnostics=diagnostics,
            )

        function_name = str(located.get("function") or "").strip()
        if not function_name:
            return ToolResult(
                success=False,
                error=f"未找到包围当前行的函数: {relative_path}:{normalized_line}",
                error_code="not_found",
                diagnostics=diagnostics,
            )

        signature = _extract_signature_lines(
            file_lines,
            start_line=located.get("start_line"),
            language=language,
        )
        parameters, return_type = _extract_symbol_signature(
            signature=signature,
            function_name=function_name,
            language=language,
        )

        degraded = any(token in resolution_method for token in ("regex", "fallback", "missing"))
        confidence = 0.55 if "regex" in resolution_method else 0.35 if "missing" in resolution_method else 0.95

        payload = {
            "file_path": relative_path,
            "line": normalized_line,
            "language": language,
            "symbol": {
                "kind": "function",
                "name": function_name,
                "start_line": located.get("start_line"),
                "end_line": located.get("end_line"),
                "signature": signature or None,
                "parameters": parameters,
                "return_type": return_type,
            },
            "resolution": {
                "method": resolution_method,
                "engine": resolution_engine,
                "confidence": confidence,
                "degraded": degraded,
            },
            "diagnostics": diagnostics,
        }

        return ToolResult(success=True, data=payload, metadata={"file_path": relative_path, **payload})
