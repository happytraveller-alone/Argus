import os
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    ".sh": "bash",
}

_LINE_KINDS = {"context", "focus", "match"}
_RENDER_TYPES = {
    "code_window",
    "search_hits",
    "execution_result",
    "outline_summary",
    "function_summary",
    "symbol_body",
    "file_list",
    "locator_result",
    "analysis_summary",
    "flow_analysis",
    "verification_summary",
    "report_summary",
}
_EXECUTION_STATUSES = {"passed", "failed", "error"}


def is_source_like_file(path_value: str) -> bool:
    ext = Path(str(path_value or "")).suffix.lower()
    return ext in _SOURCE_FILE_EXTENSIONS


def detect_language(path_value: str) -> str:
    ext = os.path.splitext(str(path_value or ""))[1].lower()
    return _LANGUAGE_BY_EXTENSION.get(ext, "text")


def unique_command_chain(commands: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in commands:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_display_command(command_chain: List[str]) -> str:
    normalized = unique_command_chain(command_chain)
    return " -> ".join(normalized) if normalized else "python"


def build_structured_lines(
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


def format_structured_lines_for_code_block(lines: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"{int(item['line_number']):4d}| {str(item.get('text') or '')}"
        for item in lines
    )


def format_structured_lines_for_search(lines: List[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for item in lines:
        line_number = int(item["line_number"])
        prefix = ">" if item.get("kind") == "match" else " "
        rows.append(f"{prefix} {line_number:4d}| {str(item.get('text') or '')}")
    return "\n".join(rows)


def build_inline_code_lines(code: str, *, language: str, focus_line: int = 1) -> Dict[str, Any]:
    text = str(code or "")
    rows = text.splitlines() or [text]
    return {
        "language": language or "text",
        "lines": build_structured_lines(rows, 1, focus_line, focus_line, "focus"),
    }


def build_execution_status(*, success: bool, error: Optional[str], exit_code: Optional[int]) -> str:
    if success:
        return "passed"
    if isinstance(exit_code, int) and exit_code not in {0, -1}:
        return "failed"
    if error:
        return "error"
    return "failed"


def validate_evidence_metadata(
    *,
    render_type: str,
    command_chain: List[str],
    display_command: str,
    entries: List[Dict[str, Any]],
) -> None:
    if render_type not in _RENDER_TYPES:
        raise ValueError(f"unsupported render_type: {render_type}")
    if not isinstance(command_chain, list) or not command_chain:
        raise ValueError("command_chain is required")
    if not isinstance(display_command, str) or not display_command.strip():
        raise ValueError("display_command is required")
    if not isinstance(entries, list):
        raise ValueError("entries is required")

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("entry must be an object")

        if render_type == "execution_result":
            _validate_execution_entry(entry)
            continue

        if render_type == "file_list":
            _validate_file_list_entry(entry)
            continue

        if render_type == "locator_result":
            _validate_locator_entry(entry)
            continue

        if render_type == "analysis_summary":
            _validate_analysis_summary_entry(entry)
            continue

        if render_type == "flow_analysis":
            _validate_flow_analysis_entry(entry)
            continue

        if render_type == "verification_summary":
            _validate_verification_summary_entry(entry)
            continue

        if render_type == "report_summary":
            _validate_report_summary_entry(entry)
            continue

        if render_type == "outline_summary":
            if not str(entry.get("file_path") or "").strip():
                raise ValueError("entry.file_path is required")
            continue

        if render_type == "function_summary":
            if not str(entry.get("file_path") or "").strip():
                raise ValueError("entry.file_path is required")
            if not str(entry.get("resolved_function") or "").strip():
                raise ValueError("entry.resolved_function is required")
            continue

        if render_type == "search_hits":
            if not str(entry.get("file_path") or "").strip():
                raise ValueError("entry.file_path is required")
            if entry.get("match_kind") != "file_summary" and not isinstance(entry.get("match_line"), int):
                raise ValueError("entry.match_line is required")
            if "match_text" not in entry:
                raise ValueError("entry.match_text is required")
            continue

        if not str(entry.get("file_path") or "").strip():
            raise ValueError("entry.file_path is required")
        if not isinstance(entry.get("lines"), list):
            raise ValueError("entry.lines is required")
        _validate_lines(entry["lines"])

        if render_type == "code_window":
            if not isinstance(entry.get("start_line"), int):
                raise ValueError("entry.start_line is required")
            if not isinstance(entry.get("end_line"), int):
                raise ValueError("entry.end_line is required")


def _validate_lines(lines: List[Dict[str, Any]]) -> None:
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("line must be an object")
        if not isinstance(line.get("line_number"), int):
            raise ValueError("line.line_number is required")
        if "text" not in line:
            raise ValueError("line.text is required")
        if str(line.get("kind") or "").strip() not in _LINE_KINDS:
            raise ValueError("line.kind is invalid")


def _validate_execution_entry(entry: Dict[str, Any]) -> None:
    if not isinstance(entry.get("exit_code"), int):
        raise ValueError("entry.exit_code is required")
    if str(entry.get("status") or "").strip() not in _EXECUTION_STATUSES:
        raise ValueError("entry.status is invalid")

    command = str(entry.get("execution_command") or "").strip()
    description = str(entry.get("description") or "").strip()
    if not command and not description:
        raise ValueError("entry.execution_command or entry.description is required")

    artifacts = entry.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            raise ValueError("entry.artifacts must be a list")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ValueError("artifact must be an object")
            if not str(artifact.get("label") or "").strip():
                raise ValueError("artifact.label is required")
            if "value" not in artifact:
                raise ValueError("artifact.value is required")

    code = entry.get("code")
    if code is not None:
        if not isinstance(code, dict):
            raise ValueError("entry.code must be an object")
        if not str(code.get("language") or "").strip():
            raise ValueError("entry.code.language is required")
        lines = code.get("lines")
        if not isinstance(lines, list):
            raise ValueError("entry.code.lines is required")
        _validate_lines(lines)


def _validate_file_list_entry(entry: Dict[str, Any]) -> None:
    if not str(entry.get("directory") or "").strip():
        raise ValueError("entry.directory is required")
    if not isinstance(entry.get("recursive"), bool):
        raise ValueError("entry.recursive is required")
    for field in ("files", "directories", "recommended_next_directories"):
        if not isinstance(entry.get(field), list):
            raise ValueError(f"entry.{field} is required")
    for field in ("file_count", "dir_count"):
        if not isinstance(entry.get(field), int):
            raise ValueError(f"entry.{field} is required")
    if not isinstance(entry.get("truncated"), bool):
        raise ValueError("entry.truncated is required")


def _validate_locator_entry(entry: Dict[str, Any]) -> None:
    if not str(entry.get("file_path") or "").strip():
        raise ValueError("entry.file_path is required")
    for field in ("line", "start_line", "end_line"):
        if not isinstance(entry.get(field), int):
            raise ValueError(f"entry.{field} is required")
    if not str(entry.get("symbol_name") or "").strip():
        raise ValueError("entry.symbol_name is required")
    if not isinstance(entry.get("parameters"), list):
        raise ValueError("entry.parameters is required")
    if not str(entry.get("engine") or "").strip():
        raise ValueError("entry.engine is required")
    if not isinstance(entry.get("confidence"), (int, float)):
        raise ValueError("entry.confidence is required")
    if not isinstance(entry.get("degraded"), bool):
        raise ValueError("entry.degraded is required")


def _validate_analysis_summary_entry(entry: Dict[str, Any]) -> None:
    for field in ("title", "summary"):
        if not str(entry.get(field) or "").strip():
            raise ValueError(f"entry.{field} is required")
    if not isinstance(entry.get("severity_stats"), dict):
        raise ValueError("entry.severity_stats is required")
    if not isinstance(entry.get("hit_count"), int):
        raise ValueError("entry.hit_count is required")
    for field in ("key_files", "highlights", "next_actions"):
        if not isinstance(entry.get(field), list):
            raise ValueError(f"entry.{field} is required")


def _validate_flow_analysis_entry(entry: Dict[str, Any]) -> None:
    for field in (
        "source_nodes",
        "sink_nodes",
        "taint_steps",
        "call_chain",
        "blocked_reasons",
        "next_actions",
    ):
        if not isinstance(entry.get(field), list):
            raise ValueError(f"entry.{field} is required")
    if not isinstance(entry.get("path_found"), bool):
        raise ValueError("entry.path_found is required")
    if not isinstance(entry.get("path_score"), (int, float)):
        raise ValueError("entry.path_score is required")
    if not isinstance(entry.get("confidence"), (int, float)):
        raise ValueError("entry.confidence is required")
    if not str(entry.get("engine") or "").strip():
        raise ValueError("entry.engine is required")
    if "reachability" not in entry:
        raise ValueError("entry.reachability is required")


def _validate_verification_summary_entry(entry: Dict[str, Any]) -> None:
    for field in ("vulnerability_type", "target", "payload", "verdict", "evidence"):
        if field not in entry:
            raise ValueError(f"entry.{field} is required")


def _validate_report_summary_entry(entry: Dict[str, Any]) -> None:
    for field in ("report_id", "title", "severity", "vulnerability_type", "location", "recommendation"):
        if field not in entry:
            raise ValueError(f"entry.{field} is required")
    if not isinstance(entry.get("verified"), bool):
        raise ValueError("entry.verified is required")
    if not isinstance(entry.get("confidence"), (int, float)):
        raise ValueError("entry.confidence is required")
    if not isinstance(entry.get("cvss_score"), (int, float)):
        raise ValueError("entry.cvss_score is required")
