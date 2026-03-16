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
import subprocess
from typing import Any, Dict, List, Optional

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


def _parse_output(output_text: str) -> Dict[str, Any]:
    text = str(output_text or "").strip()
    if not text:
        return {}

    parse_targets = [text]
    first_json_match = re.search(r"[{\[]", text)
    if first_json_match and first_json_match.start() > 0:
        parse_targets.append(text[first_json_match.start() :])

    last_error: Optional[Exception] = None
    for candidate in parse_targets:
        try:
            output = json.loads(candidate)
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
                        file_path=str(file_path or "").strip(),
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
        cmd = [
            "phpstan",
            "analyse",
            project_root,
            "--error-format=json",
            "--no-progress",
            "--no-interaction",
            f"--level={self.level}",
        ]
        process_result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        stdout_text = process_result.stdout or ""
        stderr_text = process_result.stderr or ""

        parse_error: Optional[Exception] = None
        payload: Dict[str, Any] = {}
        try:
            payload = _parse_output(stdout_text)
        except Exception as exc:  # noqa: BLE001
            parse_error = exc
            try:
                payload = _parse_output(stderr_text)
                parse_error = None
            except Exception:  # noqa: BLE001
                payload = {}

        if parse_error is not None and process_result.returncode in {0, 1}:
            raise RuntimeError(f"phpstan output parse failed: {parse_error}") from parse_error

        files_payload = payload.get("files")
        files_map: Dict[str, Any] = files_payload if isinstance(files_payload, dict) else {}
        raw_findings = _collect_raw_messages(files_map)

        if process_result.returncode > 1 and not raw_findings:
            error_message = (stderr_text or stdout_text or "unknown error").strip()
            raise RuntimeError(f"phpstan failed: {error_message[:300]}")

        findings = self._normalize_findings(files_map)
        return StaticBootstrapScanResult(
            scanner_name=self.scanner_name,
            source=self.source,
            total_findings=len(raw_findings),
            findings=findings,
            metadata={
                "timeout_seconds": self.timeout_seconds,
                "level": self.level,
            },
        )
