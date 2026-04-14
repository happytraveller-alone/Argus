"""PHPStan hybrid bootstrap scanner.

用于混合扫描（embedded static bootstrap）阶段的 PHPStan 预扫描：
- 执行 phpstan analyse 并解析 JSON 输出（兼容前缀噪声与 stderr 回退）
- 仅保留安全相关问题（五类核心 + 高危词兜底）
- 输出统一 StaticBootstrapFinding 供后续候选过滤链路复用
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import settings
from app.services.scan_path_utils import normalize_scan_file_path
from app.services.agent.scanner_runner import ScannerRunSpec, run_scanner_container
from app.services.static_scan_runtime import (
    cleanup_scan_workspace,
    copy_project_tree_to_scan_dir,
    ensure_scan_logs_dir,
    ensure_scan_meta_dir,
    ensure_scan_output_dir,
    ensure_scan_project_dir,
    ensure_scan_workspace,
)

from .base import (
    StaticBootstrapFinding,
    StaticBootstrapScanResult,
    StaticBootstrapScanner,
)


# PHPStan security filter: 五类核心 + 高危词兜底（与静态任务口径保持一致）。
_PHPSTAN_SECURITY_CORE_KEYWORDS = (
    "eval(",
    "assert(",
    "create_function",
    "exec(",
    "system(",
    "passthru(",
    "shell_exec(",
    "popen(",
    "proc_open(",
    "sql",
    "mysqli_query",
    "mysql_query",
    "pg_query",
    "pdo::query",
    "pdo::exec",
    "select ",
    "insert ",
    "update ",
    "delete ",
    "fopen(",
    "fwrite(",
    "file_get_contents(",
    "file_put_contents(",
    "unlink(",
    "copy(",
    "rename(",
    "move_uploaded_file(",
    "include(",
    "require(",
    "include_once(",
    "require_once(",
    "path traversal",
    "unserialize(",
    "maybe_unserialize(",
    "deserializ",
)

_PHPSTAN_SECURITY_FALLBACK_KEYWORDS = (
    "security",
    "unsafe",
    "dangerous",
    "injection",
    "xss",
    "rce",
    "lfi",
    "rfi",
    "xxe",
    "ssti",
    "command execution",
    "code execution",
    "remote code execution",
)


_PHPSTAN_NO_FILES_PATTERNS = (
    "no files found to analyse",
    "no files found to analyze",
)


def _is_no_files_to_analyse_output(*texts: Optional[str]) -> bool:
    combined = "\n".join(str(text or "") for text in texts).lower()
    if not combined.strip():
        return False
    return any(pattern in combined for pattern in _PHPSTAN_NO_FILES_PATTERNS)


def _parse_output(output_text: str) -> Dict[str, Any]:
    text = str(output_text or "").strip()
    if not text:
        return {}

    parse_targets = [text]
    first_object_index = text.find("{")
    if first_object_index > 0:
        parse_targets.append(text[first_object_index:])

    decoder = json.JSONDecoder()
    last_error: Optional[Exception] = None
    for candidate in parse_targets:
        try:
            output, _ = decoder.raw_decode(candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if isinstance(output, dict):
            return output
        raise ValueError("Unexpected phpstan output type")

    raise ValueError(f"Invalid phpstan JSON output: {last_error}")


def _is_security_message(message: Dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(message.get("message") or ""),
            str(message.get("identifier") or ""),
            str(message.get("tip") or ""),
        ]
    ).lower()
    if not text:
        return False
    if any(keyword in text for keyword in _PHPSTAN_SECURITY_CORE_KEYWORDS):
        return True
    return any(keyword in text for keyword in _PHPSTAN_SECURITY_FALLBACK_KEYWORDS)


def _collect_raw_messages(files_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    for file_data in files_map.values():
        if not isinstance(file_data, dict):
            continue
        file_messages = file_data.get("messages")
        if not isinstance(file_messages, list):
            continue
        for msg in file_messages:
            if isinstance(msg, dict):
                messages.append(msg)
    return messages


def _parse_plaintext_output_fallback(output_text: str) -> Dict[str, Any]:
    """Best-effort fallback for non-JSON phpstan output.

    Supports common line formats like:
    - path/to/file.php:12: message
    - message in path/to/file.php on line 12
    """
    text = str(output_text or "")
    if not text.strip():
        return {}

    files: Dict[str, Dict[str, Any]] = {}

    def _append(file_path: str, line: int, message: str) -> None:
        normalized_file = str(file_path or "").strip()
        normalized_message = str(message or "").strip()
        if not normalized_file or not normalized_message:
            return
        entry = files.setdefault(normalized_file, {"messages": []})
        entry["messages"].append(
            {
                "message": normalized_message,
                "line": int(line) if int(line) > 0 else None,
            }
        )

    colon_pattern = re.compile(
        r"^(?P<file>[^:\n]+\.php):(?P<line>\d+):\s*(?P<msg>.+)$",
        re.IGNORECASE,
    )
    in_on_line_pattern = re.compile(
        r"^(?P<msg>.+?)\s+in\s+(?P<file>[^ ]+\.php)\s+on\s+line\s+(?P<line>\d+)\s*$",
        re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matched = colon_pattern.match(line)
        if matched:
            _append(
                matched.group("file"),
                int(matched.group("line")),
                matched.group("msg"),
            )
            continue
        matched = in_on_line_pattern.match(line)
        if matched:
            _append(
                matched.group("file"),
                int(matched.group("line")),
                matched.group("msg"),
            )

    if not files:
        return {}
    return {"files": files}


class PhpstanBootstrapScanner(StaticBootstrapScanner):
    """PHPStan bootstrap scanner for hybrid embedded static pre-scan."""

    scanner_name = "phpstan"
    source = "phpstan_bootstrap"

    def __init__(self, *, level: int = 8, timeout_seconds: int = 900) -> None:
        self.level = max(0, min(9, int(level)))
        self.timeout_seconds = max(1, int(timeout_seconds))

    def _normalize_findings(
        self,
        files_map: Dict[str, Any],
    ) -> List[StaticBootstrapFinding]:
        normalized: List[StaticBootstrapFinding] = []
        index = 0
        for file_path, file_data in files_map.items():
            if not isinstance(file_data, dict):
                continue
            messages = file_data.get("messages")
            if not isinstance(messages, list):
                continue
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if not _is_security_message(msg):
                    continue

                line_value = msg.get("line")
                line = int(line_value) if isinstance(line_value, int) else None
                message_text = str(msg.get("message") or "").strip()
                identifier = str(msg.get("identifier") or "").strip()
                tip = str(msg.get("tip") or "").strip()

                title = identifier or "phpstan.security"
                description = message_text or title
                vulnerability_type = identifier or "phpstan_issue"

                normalized.append(
                    StaticBootstrapFinding(
                        id=f"phpstan-{index}",
                        title=title,
                        description=description,
                        file_path=normalize_scan_file_path(
                            str(file_path or "").strip(),
                            "/scan/project",
                        ),
                        line_start=line,
                        line_end=line,
                        code_snippet=tip or None,
                        severity="ERROR",
                        confidence="MEDIUM",
                        vulnerability_type=vulnerability_type,
                        source=self.source,
                        extra={
                            "phpstan_identifier": identifier or None,
                            "phpstan_tip": tip or None,
                            "phpstan_message": message_text,
                        },
                    )
                )
                index += 1
        return normalized

    async def scan(self, project_root: str) -> StaticBootstrapScanResult:
        task_id = f"bootstrap-{uuid4().hex}"
        workspace_dir = ensure_scan_workspace("phpstan-bootstrap", task_id)
        project_dir = ensure_scan_project_dir("phpstan-bootstrap", task_id)
        output_dir = ensure_scan_output_dir("phpstan-bootstrap", task_id)
        logs_dir = ensure_scan_logs_dir("phpstan-bootstrap", task_id)
        meta_dir = ensure_scan_meta_dir("phpstan-bootstrap", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / "report.json"

        try:
            await asyncio.to_thread(shutil.rmtree, project_dir, True)
            await asyncio.to_thread(copy_project_tree_to_scan_dir, project_root, project_dir)

            cmd = [
                "phpstan",
                "analyse",
                "/scan/project",
                "--error-format=json",
                "--no-progress",
                "--no-interaction",
                f"--level={self.level}",
            ]
            if report_file.exists():
                report_file.unlink()
            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="phpstan-bootstrap",
                    image=str(
                        getattr(settings, "SCANNER_PHPSTAN_IMAGE", "vulhunter/phpstan-runner:latest")
                    ),
                    workspace_dir=str(workspace_dir),
                    command=["php", "/opt/phpstan/phpstan", *cmd[1:]],
                    timeout_seconds=self.timeout_seconds,
                    env={},
                    expected_exit_codes=[0, 1],
                    artifact_paths=["output/report.json"],
                    capture_stdout_path="output/report.json",
                )
            )

            stderr_text = ""
            stdout_text = report_file.read_text(encoding="utf-8", errors="ignore") if report_file.exists() else ""
            if (not stdout_text.strip()) and process_result.stdout_path and Path(process_result.stdout_path).exists():
                stdout_text = Path(process_result.stdout_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            if process_result.stderr_path and Path(process_result.stderr_path).exists():
                stderr_text = Path(process_result.stderr_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            parse_error: Optional[Exception] = None
            payload: Dict[str, Any] = {}
            try:
                payload = _parse_output(stdout_text)
            except Exception as exc:  # noqa: BLE001
                parse_error = exc
                if stderr_text.strip():
                    try:
                        payload = _parse_output(stderr_text)
                        parse_error = None
                    except Exception:  # noqa: BLE001
                        payload = {}

            if not payload and stderr_text.strip() and parse_error is None:
                try:
                    payload = _parse_output(stderr_text)
                except Exception as exc:  # noqa: BLE001
                    parse_error = exc

            if parse_error is not None and process_result.exit_code in {0, 1}:
                fallback_payload = _parse_plaintext_output_fallback(stdout_text)
                if not fallback_payload and stderr_text.strip():
                    fallback_payload = _parse_plaintext_output_fallback(stderr_text)
                if fallback_payload:
                    payload = fallback_payload
                    parse_error = None

            files_payload = payload.get("files")
            files_map: Dict[str, Any] = files_payload if isinstance(files_payload, dict) else {}
            raw_findings = _collect_raw_messages(files_map)
            no_files_to_analyse = (
                process_result.exit_code in {0, 1}
                and not raw_findings
                and _is_no_files_to_analyse_output(
                    stdout_text,
                    stderr_text,
                    process_result.error,
                )
            )

            if parse_error is not None and process_result.exit_code in {0, 1} and not raw_findings:
                if no_files_to_analyse:
                    return StaticBootstrapScanResult(
                        scanner_name=self.scanner_name,
                        source=self.source,
                        total_findings=0,
                        findings=[],
                        metadata={
                            "timeout_seconds": self.timeout_seconds,
                            "level": self.level,
                            "exit_code": process_result.exit_code,
                            "parse_warning": str(parse_error)[:300],
                            "no_files_to_analyse": True,
                            "skip_reason": "no_files_found_to_analyse",
                        },
                    )
                preview = (stderr_text or stdout_text or process_result.error or "").strip()[:300]
                raise RuntimeError(
                    f"phpstan output parse failed: {parse_error}. output preview: {preview}"
                ) from parse_error

            if process_result.exit_code > 1 and not raw_findings:
                error_message = (stderr_text or stdout_text or process_result.error or "unknown error").strip()
                raise RuntimeError(f"phpstan failed: {error_message[:300]}")

            if no_files_to_analyse:
                return StaticBootstrapScanResult(
                    scanner_name=self.scanner_name,
                    source=self.source,
                    total_findings=0,
                    findings=[],
                    metadata={
                        "timeout_seconds": self.timeout_seconds,
                        "level": self.level,
                        "exit_code": process_result.exit_code,
                        "parse_warning": str(parse_error)[:300] if parse_error is not None else None,
                        "no_files_to_analyse": True,
                        "skip_reason": "no_files_found_to_analyse",
                    },
                )

            findings = self._normalize_findings(files_map)
            return StaticBootstrapScanResult(
                scanner_name=self.scanner_name,
                source=self.source,
                total_findings=len(raw_findings),
                findings=findings,
                metadata={
                    "timeout_seconds": self.timeout_seconds,
                    "level": self.level,
                    "exit_code": process_result.exit_code,
                    "parse_warning": str(parse_error)[:300] if parse_error is not None else None,
                },
            )
        finally:
            cleanup_scan_workspace("phpstan-bootstrap", task_id)
