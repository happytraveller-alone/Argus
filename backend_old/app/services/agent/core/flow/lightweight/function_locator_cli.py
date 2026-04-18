from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_PSEUDO_FUNCTION_NAMES = {"__attribute__", "__declspec"}
_CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "else", "return"}


def _is_pseudo_function_name(name: Optional[str]) -> bool:
    if not isinstance(name, str):
        return False
    normalized = name.strip().lower()
    return normalized in _PSEUDO_FUNCTION_NAMES


def _detect_block_end(
    lines: List[str],
    start_index: int,
    language: str,
) -> int:
    if language == "python":
        indent = len(lines[start_index]) - len(lines[start_index].lstrip(" "))
        end = start_index + 1
        for idx in range(start_index + 1, len(lines)):
            probe = lines[idx]
            stripped = probe.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "@")):
                continue
            probe_indent = len(probe) - len(probe.lstrip(" "))
            if probe_indent <= indent:
                break
            end = idx + 1
        return end

    balance = 0
    end = start_index + 1
    for idx in range(start_index, len(lines)):
        probe = lines[idx]
        balance += probe.count("{")
        balance -= probe.count("}")
        end = idx + 1
        if idx > start_index and balance <= 0:
            break
    return end


def _regex_locate_enclosing_function(
    *,
    file_lines: List[str],
    line_start: int,
    language: str,
) -> Tuple[Optional[str], Optional[int], Optional[int], str]:
    if not file_lines:
        return None, None, None, "regex_empty_file"

    start_idx = max(0, min(len(file_lines) - 1, int(line_start) - 1))
    patterns: List[re.Pattern[str]] = []

    if language == "python":
        patterns = [re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")]
    elif language in {"javascript", "typescript", "tsx"}:
        patterns = [
            re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"^\s*(?:public|private|protected|static|async|\s)*([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"),
        ]
    elif language == "java":
        patterns = [
            re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\], ?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"),
            re.compile(r"^\s*(?:public|private|protected)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"),
        ]
    elif language == "kotlin":
        patterns = [re.compile(r"^\s*(?:public|private|protected|internal|open|override|suspend|inline|tailrec|operator|infix|\s)*fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")]
    elif language in {"c", "cpp"}:
        patterns = [re.compile(r"^\s*(?:[A-Za-z_~][\w:<>,\s]*\s+)?[*&\s]*([A-Za-z_~][A-Za-z0-9_:]*)\s*\([^;]*\)\s*(?:const)?\s*(?:noexcept)?\s*\{?$")]

    for idx in range(start_idx, -1, -1):
        line = file_lines[idx]
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("//", "#")):
            continue

        if language in {"c", "cpp"}:
            candidate_names = [
                str(name or "").strip()
                for name in re.findall(r"([A-Za-z_~][A-Za-z0-9_:]*)\s*\(", line)
            ]
            candidate_names = [
                name
                for name in candidate_names
                if name
                and name.lower() not in _CONTROL_KEYWORDS
                and not _is_pseudo_function_name(name)
            ]
            if candidate_names:
                name = candidate_names[-1]
                start_line = idx + 1
                end_line = _detect_block_end(file_lines, idx, language)
                if start_line <= line_start <= end_line:
                    return name, start_line, end_line, "regex_enclosing_match"

        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue

            name = str(match.group(1) or "").strip()
            if not name:
                continue
            if name.lower() in _CONTROL_KEYWORDS or _is_pseudo_function_name(name):
                continue

            start_line = idx + 1
            end_line = _detect_block_end(file_lines, idx, language)
            if start_line <= line_start <= end_line:
                return name, start_line, end_line, "regex_enclosing_match"

    return None, None, None, "regex_no_match"


def locate_with_tree_sitter_cli(
    *,
    file_path: str,
    line_start: int,
    language: str,
    file_lines: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Best-effort CLI fallback.

    Python tree-sitter binding is the primary engine. CLI fallback is non-blocking:
    if CLI is unavailable or parsing fails, return diagnostics and keep flow running.
    """
    diagnostics: List[str] = []
    target_path = Path(file_path)

    cli_bin = shutil.which("tree-sitter")
    if not cli_bin:
        diagnostics.append("tree_sitter_cli_unavailable")
    else:
        try:
            proc = subprocess.run(
                [cli_bin, "parse", str(target_path), "--quiet"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                diagnostics.append(f"tree_sitter_cli_parse_failed:{stderr[:200] or proc.returncode}")
            else:
                diagnostics.append("tree_sitter_cli_parse_ok_no_symbol_extraction")
        except Exception as exc:
            diagnostics.append(f"tree_sitter_cli_error:{type(exc).__name__}")

    lines = file_lines
    if lines is None:
        try:
            lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            lines = []
            diagnostics.append("tree_sitter_cli_file_read_failed")

    name, start_line, end_line, regex_reason = _regex_locate_enclosing_function(
        file_lines=lines,
        line_start=line_start,
        language=language,
    )
    diagnostics.append(regex_reason)

    return {
        "function": name,
        "start_line": start_line,
        "end_line": end_line,
        "language": language,
        "resolution_engine": "tree_sitter_cli_regex",
        "resolution_method": "tree_sitter_cli_regex",
        "diagnostics": diagnostics,
    }
