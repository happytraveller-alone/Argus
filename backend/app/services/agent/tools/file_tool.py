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
from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult


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


def _is_source_like_file(path_value: str) -> bool:
    ext = Path(str(path_value or "")).suffix.lower()
    return ext in _SOURCE_FILE_EXTENSIONS


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


class FileReadInput(BaseModel):
    """文件读取输入"""
    file_path: str = Field(description="文件路径（相对于项目根目录）")
    start_line: Optional[int] = Field(default=None, description="起始行号（从1开始）")
    end_line: Optional[int] = Field(default=None, description="结束行号")
    max_lines: int = Field(default=500, description="最大返回行数")
    reason_paths: Optional[List[str]] = Field(default=None, description="可选，基于上文推断的优先路径")
    project_scope: bool = Field(default=True, description="可选，启用全项目路径补全")
    strict_anchor: bool = Field(default=False, description="严格锚点模式：仅允许窗口化读取")
    allow_file_header_fallback: bool = Field(
        default=False,
        description="严格锚点模式下允许回退读取文件头部窗口（防御性兜底）。",
    )


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
        strict_anchor_mode: bool = False,
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
        self.target_files = (
            {_normalize_rel_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )
        self.strict_anchor_mode = bool(strict_anchor_mode)

    @staticmethod
    def _read_all_lines_sync(file_path: str) -> List[str]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()

    @staticmethod
    def _count_lines_fast_sync(file_path: str) -> int:
        try:
            proc = subprocess.run(
                ["wc", "-l", file_path],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                prefix = str(proc.stdout or "").strip().split(" ", 1)[0]
                if prefix.isdigit():
                    return int(prefix)
        except Exception:
            pass
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)

    @staticmethod
    def _read_lines_by_range_sync(file_path: str, start_line: int, end_line: int) -> List[str]:
        try:
            proc = subprocess.run(
                ["sed", "-n", f"{start_line},{end_line}p", file_path],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return str(proc.stdout or "").splitlines()
        except Exception:
            pass

        lines: List[str] = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                if idx < start_line:
                    continue
                if idx > end_line:
                    break
                lines.append(line.rstrip("\n"))
        return lines

    @staticmethod
    def _read_lines_head_sync(file_path: str, max_lines: int) -> List[str]:
        safe_lines = max(1, int(max_lines))
        try:
            proc = subprocess.run(
                ["head", "-n", str(safe_lines), file_path],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return str(proc.stdout or "").splitlines()
        except Exception:
            pass

        lines: List[str] = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                if idx > safe_lines:
                    break
                lines.append(line.rstrip("\n"))
        return lines

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

注意: 为避免输出过长，建议指定行范围或使用 RAG 搜索定位代码。"""
    
    @property
    def args_schema(self):
        return FileReadInput
    
    def _should_exclude(self, file_path: str) -> bool:
        """检查文件是否应该被排除"""
        normalized_path = _normalize_rel_path(file_path)
        if _has_hidden_or_test_segment(normalized_path):
            return True
        # 如果指定了目标文件，只允许读取这些文件
        if self.target_files and normalized_path not in self.target_files:
            return True
        
        # 检查排除模式
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(normalized_path, pattern):
                return True
            # 也检查文件名
            if fnmatch.fnmatch(os.path.basename(normalized_path), pattern):
                return True
        
        return False
    
    def _collect_reason_dirs(self, reason_paths: Optional[List[str]]) -> List[str]:
        if not isinstance(reason_paths, list):
            return []
        normalized: List[str] = []
        seen: set[str] = set()
        for item in reason_paths:
            norm = _normalize_reason_path(item, self.project_root)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            normalized.append(norm)
            if len(normalized) >= 12:
                break
        return normalized

    def _resolve_existing_file(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        candidate = str(file_path or "").strip().replace("\\", "/")
        if not candidate:
            return None, None

        root_norm = os.path.normpath(self.project_root)
        if os.path.isabs(candidate):
            abs_norm = os.path.normpath(candidate)
            if not abs_norm.startswith(root_norm):
                return None, None
            if os.path.isfile(abs_norm):
                rel = _normalize_display_path(abs_norm, self.project_root)
                return rel, abs_norm
            return None, None

        full_path = os.path.normpath(os.path.join(self.project_root, candidate))
        if not full_path.startswith(root_norm):
            return None, None
        if os.path.isfile(full_path):
            rel = _normalize_display_path(full_path, self.project_root)
            return rel, full_path
        return None, None

    def _scan_project_for_path_candidates(
        self,
        target_path: str,
        reason_dirs: List[str],
        project_scope: bool,
    ) -> List[Dict[str, Any]]:
        normalized_target = _normalize_rel_path(target_path)
        basename = os.path.basename(normalized_target)
        if not normalized_target or (not project_scope and not reason_dirs):
            return []

        matches: List[Dict[str, Any]] = []
        files_scanned = 0
        for root, dirs, files in os.walk(self.project_root):
            rel_dir = os.path.relpath(root, self.project_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d for d in dirs
                if d not in {"node_modules", "vendor", "dist", "build", ".git", "__pycache__", ".pytest_cache"}
                and not d.startswith(".")
                and not _has_hidden_or_test_segment(f"{rel_dir}/{d}" if rel_dir else d)
            ]

            for filename in files:
                files_scanned += 1
                if files_scanned > 10000:
                    return matches

                rel_path = _normalize_rel_path(os.path.join(rel_dir, filename) if rel_dir else filename)
                if not rel_path or _has_hidden_or_test_segment(rel_path):
                    continue
                if self._should_exclude(rel_path):
                    continue
                if not _is_source_like_file(rel_path):
                    continue

                suffix_hit = bool(normalized_target and rel_path.endswith(normalized_target))
                basename_hit = bool(basename and filename == basename)
                if not suffix_hit and not basename_hit:
                    continue

                score = 0
                if suffix_hit:
                    score += 300
                elif basename_hit:
                    score += 200

                if reason_dirs:
                    for idx, reason in enumerate(reason_dirs):
                        prefix = reason.rstrip("/")
                        if rel_path == prefix or rel_path.startswith(f"{prefix}/"):
                            score += max(1, 30 - idx)
                            break

                score += max(0, 8 - rel_path.count("/"))
                matches.append(
                    {
                        "relative_path": rel_path,
                        "full_path": os.path.join(self.project_root, rel_path),
                        "score": score,
                        "suffix_hit": suffix_hit,
                        "basename_hit": basename_hit,
                    }
                )
        return matches

    def _resolve_file_with_context(
        self,
        file_path: str,
        reason_paths: Optional[List[str]],
        project_scope: bool,
    ) -> tuple[Optional[str], Optional[str], Optional[str], List[str]]:
        raw_input_path = str(file_path or "").strip().replace("\\", "/")
        direct_rel, direct_abs = self._resolve_existing_file(file_path)
        reason_dirs = self._collect_reason_dirs(reason_paths)
        if not raw_input_path:
            return None, None, "必须提供 file_path", reason_dirs
        root_norm = os.path.normpath(self.project_root)
        if not os.path.isabs(raw_input_path):
            try:
                resolved_candidate = os.path.normpath(
                    os.path.join(self.project_root, raw_input_path)
                )
                if os.path.commonpath([root_norm, resolved_candidate]) != root_norm:
                    return None, None, "安全错误：不允许读取项目目录外的文件", reason_dirs
            except Exception:
                return None, None, "安全错误：不允许读取项目目录外的文件", reason_dirs
        if os.path.isabs(raw_input_path):
            try:
                input_norm = os.path.normpath(raw_input_path)
                if os.path.commonpath([root_norm, input_norm]) != root_norm:
                    return None, None, "安全错误：不允许读取项目目录外的文件", reason_dirs
            except Exception:
                return None, None, "安全错误：不允许读取项目目录外的文件", reason_dirs

        if direct_rel and direct_abs:
            return direct_rel, direct_abs, None, reason_dirs

        matches = self._scan_project_for_path_candidates(file_path, reason_dirs, project_scope)
        if not matches:
            if project_scope:
                return None, None, f"文件不存在: {file_path}（已在项目范围内尝试路径补全）", reason_dirs
            return None, None, f"文件不存在: {file_path}", reason_dirs

        suffix_matches = [item for item in matches if item.get("suffix_hit")]
        if suffix_matches:
            suffix_matches.sort(key=lambda item: (item["score"], -len(item["relative_path"])), reverse=True)
            winner = suffix_matches[0]
            return winner["relative_path"], winner["full_path"], None, reason_dirs

        basename_matches = [item for item in matches if item.get("basename_hit")]
        if len(basename_matches) == 1:
            winner = basename_matches[0]
            return winner["relative_path"], winner["full_path"], None, reason_dirs

        basename_matches.sort(key=lambda item: (item["score"], -len(item["relative_path"])), reverse=True)
        winner = basename_matches[0]
        return winner["relative_path"], winner["full_path"], None, reason_dirs

    async def _execute(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_lines: int = 500,
        reason_paths: Optional[List[str]] = None,
        project_scope: bool = True,
        strict_anchor: bool = False,
        allow_file_header_fallback: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            parsed_path, parsed_start_line, parsed_end_line = _parse_file_path_with_line_range(file_path)
            file_path = parsed_path
            if start_line is None and end_line is None and parsed_start_line is not None:
                start_line = parsed_start_line
                end_line = parsed_end_line

            strict_anchor_enabled = bool(strict_anchor) or bool(self.strict_anchor_mode)
            if strict_anchor_enabled and start_line is None and end_line is None:
                if bool(allow_file_header_fallback) and str(file_path or "").strip():
                    start_line = 1
                    end_line = 120
                else:
                    return ToolResult(
                        success=False,
                        error="read_file 严格锚点模式要求提供 start_line/end_line，禁止无定位全文读取。",
                        metadata={
                            "strict_anchor": True,
                            "read_scope_policy": "strict_anchor",
                        },
                    )

            resolved_rel_path, full_path, resolve_error, normalized_reason_dirs = await asyncio.to_thread(
                self._resolve_file_with_context,
                file_path,
                reason_paths,
                bool(project_scope),
            )
            if resolve_error or not resolved_rel_path or not full_path:
                return ToolResult(success=False, error=resolve_error or f"文件不存在: {file_path}")

            if self._should_exclude(resolved_rel_path):
                return ToolResult(
                    success=False,
                    error=f"文件被排除或不在目标文件列表中: {resolved_rel_path}",
                )

            if not os.path.exists(full_path):
                return ToolResult(success=False, error=f"文件不存在: {resolved_rel_path}")
            if not os.path.isfile(full_path):
                return ToolResult(success=False, error=f"不是文件: {resolved_rel_path}")

            total_lines = await asyncio.to_thread(self._count_lines_fast_sync, full_path)
            safe_max_lines = max(1, min(int(max_lines or 500), 2000))

            if total_lines <= 0:
                return ToolResult(
                    success=True,
                    data=f"文件: {resolved_rel_path}\n行数: 0-0 / 0\n\n```text\n\n```",
                    metadata={
                        "file_path": resolved_rel_path,
                        "total_lines": 0,
                        "start_line": 0,
                        "end_line": 0,
                        "language": "text",
                        "reason_paths_used": normalized_reason_dirs,
                        "strict_anchor": strict_anchor_enabled,
                    },
                )

            if start_line is not None or end_line is not None:
                start_val = max(1, int(start_line or 1))
                if end_line is None:
                    end_val = min(total_lines, start_val + safe_max_lines - 1)
                else:
                    end_val = min(total_lines, max(start_val, int(end_line)))
                selected_lines = await asyncio.to_thread(
                    self._read_lines_by_range_sync,
                    full_path,
                    start_val,
                    end_val,
                )
                display_start = start_val
                display_end = start_val + max(len(selected_lines) - 1, 0)
            else:
                selected_lines = await asyncio.to_thread(
                    self._read_lines_head_sync,
                    full_path,
                    safe_max_lines,
                )
                display_start = 1
                display_end = len(selected_lines)

            numbered_lines = []
            for idx, line in enumerate(selected_lines, start=display_start):
                numbered_lines.append(f"{idx:4d}| {line.rstrip()}")
            content = "\n".join(numbered_lines)

            ext = os.path.splitext(resolved_rel_path)[1].lower()
            language = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".go": "go", ".rs": "rust",
                ".cpp": "cpp", ".c": "c", ".cs": "csharp",
                ".php": "php", ".rb": "ruby", ".swift": "swift",
            }.get(ext, "text")

            output = f"文件: {resolved_rel_path}\n"
            output += f"行数: {display_start}-{display_end} / {total_lines}\n\n"
            output += f"```{language}\n{content}\n```"
            if display_end < total_lines:
                output += f"\n\n... 还有 {total_lines - display_end} 行未显示"

            return ToolResult(
                success=True,
                data=output,
                metadata={
                    "file_path": resolved_rel_path,
                    "total_lines": total_lines,
                    "start_line": display_start,
                    "end_line": display_end,
                    "language": language,
                    "reason_paths_used": normalized_reason_dirs,
                    "project_scope": bool(project_scope),
                    "strict_anchor": strict_anchor_enabled,
                    "read_anchor_source": (
                        "file_header_fallback"
                        if bool(allow_file_header_fallback) and int(display_start) == 1 and int(display_end) <= 120
                        else "input"
                    ),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"读取文件失败: {str(e)}")


class FileSearchInput(BaseModel):
    """文件搜索输入"""
    keyword: str = Field(description="搜索关键字或正则表达式")
    file_pattern: Optional[str] = Field(default=None, description="文件名模式，如 *.py, *.js")
    directory: Optional[str] = Field(default=None, description="搜索目录（相对路径）")
    case_sensitive: bool = Field(default=False, description="是否区分大小写")
    max_results: int = Field(default=50, description="最大结果数")
    is_regex: bool = Field(default=False, description="是否使用正则表达式")


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
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()

    @staticmethod
    def _is_path_within_root(candidate_path: str, root_path: str) -> bool:
        try:
            return os.path.commonpath(
                [os.path.normpath(candidate_path), os.path.normpath(root_path)]
            ) == os.path.normpath(root_path)
        except Exception:
            return False

    def _normalize_directory(self, directory: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        root_norm = os.path.normpath(self.project_root)
        raw = str(directory or "").strip().replace("\\", "/")
        if not raw or raw == ".":
            return ".", self.project_root, None

        if os.path.isabs(raw):
            search_dir = os.path.normpath(raw)
            if not self._is_path_within_root(search_dir, root_norm):
                return None, None, "安全错误：不允许搜索项目目录外的内容"
            rel = os.path.relpath(search_dir, self.project_root).replace("\\", "/")
            rel = "." if rel == "." else _normalize_rel_path(rel)
        else:
            rel = _normalize_rel_path(raw)
            search_dir = os.path.normpath(os.path.join(self.project_root, rel))
            if not self._is_path_within_root(search_dir, root_norm):
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

    def _build_context_block(
        self,
        full_path: str,
        line_number: int,
        cache: Dict[str, List[str]],
    ) -> str:
        lines = cache.get(full_path)
        if lines is None:
            try:
                lines = self._read_file_lines_sync(full_path)
            except Exception:
                return f"> {line_number:4d}| <无法读取上下文>"
            cache[full_path] = lines

        start = max(1, line_number - 1)
        end = min(len(lines), line_number + 1)
        context_rows: List[str] = []
        for cursor in range(start, end + 1):
            prefix = ">" if cursor == line_number else " "
            text = lines[cursor - 1].rstrip("\n")
            context_rows.append(f"{prefix} {cursor:4d}| {text}")
        return "\n".join(context_rows)

    def _build_rg_command(
        self,
        keyword: str,
        search_dir: str,
        normalized_patterns: List[str],
        case_sensitive: bool,
        is_regex: bool,
    ) -> List[str]:
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never", "--max-columns", "300"]
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
        file_context_cache: Dict[str, List[str]] = {}
        matched_files: set[str] = set()
        seen_key: set[tuple[str, int]] = set()
        stdout_text = str(proc.stdout or "")
        for raw_line in stdout_text.splitlines():
            parts = raw_line.split(":", 2)
            if len(parts) < 3:
                continue
            path_part, line_part, match_part = parts[0], parts[1], parts[2]
            try:
                line_number = int(line_part)
            except Exception:
                continue

            full_path = os.path.normpath(path_part)
            if not self._is_path_within_root(full_path, self.project_root):
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
            matched_files.add(relative_path)

            context = self._build_context_block(full_path, line_number, file_context_cache)
            results.append(
                {
                    "file": relative_path,
                    "line": line_number,
                    "match": str(match_part or "").strip()[:200],
                    "context": context,
                }
            )
            if len(results) >= max_results:
                break

        return results, len(matched_files)

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
        file_context_cache: Dict[str, List[str]] = {}
        matched_files: set[str] = set()
        seen_key: set[tuple[str, int]] = set()
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
            if not self._is_path_within_root(full_path, self.project_root):
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
            matched_files.add(relative_path)

            context = self._build_context_block(full_path, line_number, file_context_cache)
            results.append(
                {
                    "file": relative_path,
                    "line": line_number,
                    "match": str(match_part or "").strip()[:200],
                    "context": context,
                }
            )
            if len(results) >= max_results:
                break

        return results, len(matched_files)

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
        files_searched = 0

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
                files_searched += 1
                for idx, line in enumerate(lines, start=1):
                    if not pattern.search(line):
                        continue
                    start = max(1, idx - 1)
                    end = min(len(lines), idx + 1)
                    context_rows: List[str] = []
                    for cursor in range(start, end + 1):
                        prefix = ">" if cursor == idx else " "
                        context_rows.append(
                            f"{prefix} {cursor:4d}| {lines[cursor - 1].rstrip()}"
                        )
                    results.append(
                        {
                            "file": relative_path,
                            "line": idx,
                            "match": line.strip()[:200],
                            "context": "\n".join(context_rows),
                        }
                    )
                    if len(results) >= max_results:
                        return results, files_searched
        return results, files_searched

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
- directory: 可选，搜索目录
- case_sensitive: 是否区分大小写
- is_regex: 是否使用正则表达式

这是一个快速搜索工具，结果包含匹配行和上下文。"""
    
    @property
    def args_schema(self):
        return FileSearchInput
    
    async def _execute(
        self,
        keyword: str,
        file_pattern: Optional[str] = None,
        directory: Optional[str] = None,
        case_sensitive: bool = False,
        max_results: int = 50,
        is_regex: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            normalized_patterns = _split_file_patterns(file_pattern)
            search_dir_rel, search_dir_abs, dir_error = self._normalize_directory(directory)
            if dir_error or not search_dir_abs or not search_dir_rel:
                return ToolResult(success=False, error=dir_error or "搜索目录解析失败")

            if is_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    re.compile(keyword, flags)
                except re.error as exc:
                    return ToolResult(success=False, error=f"无效的搜索模式: {exc}")

            safe_max_results = max(1, min(int(max_results or 50), 200))
            results, files_searched, engine = await asyncio.to_thread(
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
            if not results and search_dir_rel not in {"", "."}:
                fallback_results, fallback_files_searched, fallback_engine = await asyncio.to_thread(
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
                    files_searched = fallback_files_searched
                    engine = fallback_engine

            if not results:
                return ToolResult(
                    success=True,
                    data=(
                        f"没有找到匹配 '{keyword}' 的内容\n"
                        f"搜索目录: {effective_directory}\n"
                        f"执行引擎: {engine}\n"
                        f"搜索文件数: {files_searched}"
                    ),
                    metadata={
                        "keyword": keyword,
                        "files_searched": files_searched,
                        "matches": 0,
                        "normalized_file_patterns": normalized_patterns,
                        "engine": engine,
                        "scope_fallback_applied": scope_fallback_applied,
                        "original_directory": search_dir_rel,
                        "effective_directory": effective_directory,
                    },
                )

            output_parts = [
                f"搜索关键字: '{keyword}'",
                f"匹配数: {len(results)}（搜索文件数: {files_searched}）",
                f"执行引擎: {engine}",
            ]
            for item in results:
                output_parts.append(f"\n{item['file']}:{item['line']}")
                output_parts.append(f"```\n{item['context']}\n```")
            if len(results) >= safe_max_results:
                output_parts.append(f"\n结果已截断（最大 {safe_max_results} 条）")

            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "keyword": keyword,
                    "files_searched": files_searched,
                    "matches": len(results),
                    "normalized_file_patterns": normalized_patterns,
                    "results": results[:10],
                    "engine": engine,
                    "scope_fallback_applied": scope_fallback_applied,
                    "original_directory": search_dir_rel,
                    "effective_directory": effective_directory,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {str(e)}")


class ListFilesInput(BaseModel):
    """列出文件输入"""
    directory: str = Field(default=".", description="目录路径（相对于项目根目录）")
    pattern: Optional[str] = Field(default=None, description="文件名模式，如 *.py")
    recursive: bool = Field(default=False, description="是否递归列出子目录")
    max_files: int = Field(default=100, description="最大文件数")


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
- directory: 目录路径
- pattern: 可选，文件名模式
- recursive: 是否递归
- max_files: 最大文件数"""
    
    @property
    def args_schema(self):
        return ListFilesInput
    
    async def _execute(
        self,
        directory: str = ".",
        pattern: Optional[str] = None,
        recursive: bool = False,
        max_files: int = 100,
        **kwargs
    ) -> ToolResult:
        """执行文件列表"""
        try:
            # 🔥 兼容性处理：支持 path 参数作为 directory 的别名
            if "path" in kwargs and kwargs["path"]:
                directory = kwargs["path"]

            target_dir = os.path.normpath(os.path.join(self.project_root, directory))
            if not target_dir.startswith(os.path.normpath(self.project_root)):
                return ToolResult(
                    success=False,
                    error="安全错误：不允许访问项目目录外的目录",
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
                output_parts.append(f"⚠️ 注意: 审计范围限定为 {len(self.target_files)} 个指定文件\n")
            
            if dirs:
                output_parts.append("目录:")
                for d in sorted(dirs)[:20]:
                    output_parts.append(f"  📂 {d}")
                if len(dirs) > 20:
                    output_parts.append(f"  ... 还有 {len(dirs) - 20} 个目录")
            
            if files:
                output_parts.append(f"\n文件 ({len(files)}):")
                for f in sorted(files):
                    output_parts.append(f"  📄 {f}")
            elif self.target_files:
                # 如果没有文件但设置了 target_files，显示目标文件列表
                output_parts.append(f"\n指定的目标文件 ({len(self.target_files)}):")
                for f in sorted(self.target_files)[:20]:
                    output_parts.append(f"  📄 {f}")
                if len(self.target_files) > 20:
                    output_parts.append(f"  ... 还有 {len(self.target_files) - 20} 个文件")
            
            if len(files) >= max_files:
                output_parts.append(f"\n... 结果已截断（最大 {max_files} 个文件）")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "directory": directory,
                    "file_count": len(files),
                    "dir_count": len(dirs),
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"列出文件失败: {str(e)}",
            )
