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


def _normalize_confidence(value: Any) -> Optional[str]:
    normalized = str(value or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _normalize_severity_to_bootstrap_error(value: Any) -> str:
    # Keep existing bootstrap filter contract:
    # only severity == ERROR survives candidate filtering.
    normalized = str(value or "").strip().upper()
    if normalized == "HIGH":
        return "ERROR"
    return "WARNING"


def _parse_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout:
        return []

    text = stdout.strip()
    if not text:
        return []

    # Bandit may prepend log lines in some environments.
    # Try to decode from the first JSON token if direct parse fails.
    parse_targets = [text]
    first_json_match = re.search(r"[{\[]", text)
    if first_json_match and first_json_match.start() > 0:
        parse_targets.append(text[first_json_match.start():])

    output: Any = None
    last_error: Optional[Exception] = None
    for candidate in parse_targets:
        try:
            output = json.loads(candidate)
            break
        except Exception as exc:  # noqa: BLE001 - keep last error for context
            last_error = exc
            continue

    if output is None:
        raise ValueError(f"Invalid bandit JSON output: {last_error}")

    if isinstance(output, dict):
        results = output.get("results", [])
    elif isinstance(output, list):
        results = output
    else:
        raise ValueError("Unexpected bandit output type")

    if not isinstance(results, list):
        raise ValueError("Invalid bandit results format")

    parsed: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


class BanditBootstrapScanner(StaticBootstrapScanner):
    """Bandit bootstrap scanner for hybrid embedded static pre-scan."""

    scanner_name = "bandit"
    source = "bandit_bootstrap"

    def __init__(self, *, timeout_seconds: int = 900) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))

    def _normalize_findings(
        self,
        payload_findings: List[Dict[str, Any]],
    ) -> List[StaticBootstrapFinding]:
        normalized: List[StaticBootstrapFinding] = []
        for index, payload in enumerate(payload_findings):
            test_id = str(payload.get("test_id") or "").strip()
            test_name = str(payload.get("test_name") or "").strip()
            issue_text = str(payload.get("issue_text") or "").strip()
            file_path = str(payload.get("filename") or "").strip()
            line_number = int(payload.get("line_number") or 0)
            issue_severity = str(payload.get("issue_severity") or "").strip().upper()
            issue_confidence = _normalize_confidence(payload.get("issue_confidence"))

            title = test_name or test_id or "Bandit 发现"
            description = issue_text or title
            code_snippet = payload.get("code")
            vuln_type = test_id or "bandit_issue"
            severity = _normalize_severity_to_bootstrap_error(issue_severity)

            normalized.append(
                StaticBootstrapFinding(
                    id=f"bandit-{index}",
                    title=title,
                    description=description,
                    file_path=file_path,
                    line_start=line_number or None,
                    line_end=line_number or None,
                    code_snippet=str(code_snippet) if code_snippet is not None else None,
                    severity=severity,
                    confidence=issue_confidence,
                    vulnerability_type=vuln_type,
                    source=self.source,
                    extra={
                        "bandit_issue_severity": issue_severity,
                        "bandit_issue_confidence": issue_confidence,
                    },
                )
            )
        return normalized

    async def scan(self, project_root: str) -> StaticBootstrapScanResult:
        # Use quiet mode to reduce non-JSON log noise in output streams.
        cmd = ["bandit", "-q", "-r", "-f", "json", project_root]
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
        payload_findings: List[Dict[str, Any]] = []
        try:
            payload_findings = _parse_output(stdout_text)
        except Exception as exc:  # noqa: BLE001
            parse_error = exc
            # Some runtimes may put payload into stderr; attempt fallback parse.
            try:
                payload_findings = _parse_output(stderr_text)
                parse_error = None
            except Exception:  # noqa: BLE001
                payload_findings = []

        if parse_error is not None and process_result.returncode in {0, 1}:
            raise RuntimeError(f"bandit output parse failed: {parse_error}") from parse_error

        if process_result.returncode != 0 and not payload_findings:
            message = (stderr_text or stdout_text or "unknown error").strip()
            raise RuntimeError(f"bandit failed: {message[:300]}")

        findings = self._normalize_findings(payload_findings)
        return StaticBootstrapScanResult(
            scanner_name=self.scanner_name,
            source=self.source,
            total_findings=len(payload_findings),
            findings=findings,
            metadata={
                "timeout_seconds": self.timeout_seconds,
            },
        )
