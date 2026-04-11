from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.api.v1.endpoints.static_tasks_shared import (
    cleanup_scan_workspace,
    copy_project_tree_to_scan_dir,
    ensure_scan_logs_dir,
    ensure_scan_meta_dir,
    ensure_scan_output_dir,
    ensure_scan_project_dir,
    ensure_scan_workspace,
)
from app.core.config import settings
from app.services.scan_path_utils import normalize_scan_file_path
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container

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

    def __init__(
        self,
        *,
        timeout_seconds: int = 900,
        rule_ids: Optional[List[str]] = None,
    ) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        normalized_rule_ids: List[str] = []
        for raw in rule_ids or []:
            normalized = str(raw or "").strip().upper()
            if not normalized:
                continue
            if normalized not in normalized_rule_ids:
                normalized_rule_ids.append(normalized)
        self.rule_ids = normalized_rule_ids

    def _normalize_findings(
        self,
        payload_findings: List[Dict[str, Any]],
    ) -> List[StaticBootstrapFinding]:
        normalized: List[StaticBootstrapFinding] = []
        for index, payload in enumerate(payload_findings):
            test_id = str(payload.get("test_id") or "").strip()
            test_name = str(payload.get("test_name") or "").strip()
            issue_text = str(payload.get("issue_text") or "").strip()
            file_path = normalize_scan_file_path(
                str(payload.get("filename") or "").strip(),
                "/scan/project",
            )
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
        task_id = f"bootstrap-{uuid4().hex}"
        workspace_dir = ensure_scan_workspace("bandit-bootstrap", task_id)
        project_dir = ensure_scan_project_dir("bandit-bootstrap", task_id)
        output_dir = ensure_scan_output_dir("bandit-bootstrap", task_id)
        logs_dir = ensure_scan_logs_dir("bandit-bootstrap", task_id)
        meta_dir = ensure_scan_meta_dir("bandit-bootstrap", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / "report.json"

        try:
            await asyncio.to_thread(shutil.rmtree, project_dir, True)
            await asyncio.to_thread(copy_project_tree_to_scan_dir, project_root, project_dir)

            cmd = [
                "bandit",
                "-r",
                "/scan/project",
                "-f",
                "json",
                "-o",
                "/scan/output/report.json",
                "-q",
            ]
            if self.rule_ids:
                cmd.extend(["-t", ",".join(self.rule_ids)])
            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="bandit-bootstrap",
                    image=str(
                        getattr(settings, "SCANNER_BANDIT_IMAGE", "vulhunter/bandit-runner:latest")
                    ),
                    workspace_dir=str(workspace_dir),
                    command=cmd,
                    timeout_seconds=self.timeout_seconds,
                    env={},
                    expected_exit_codes=[0, 1],
                    artifact_paths=["output/report.json"],
                )
            )

            stdout_text = ""
            stderr_text = ""
            if process_result.stdout_path and Path(process_result.stdout_path).exists():
                stdout_text = Path(process_result.stdout_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            if process_result.stderr_path and Path(process_result.stderr_path).exists():
                stderr_text = Path(process_result.stderr_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            payload_findings: List[Dict[str, Any]] = []
            parse_error: Optional[Exception] = None
            if report_file.exists():
                try:
                    payload_findings = _parse_output(
                        report_file.read_text(encoding="utf-8", errors="ignore")
                    )
                except Exception as exc:  # noqa: BLE001
                    parse_error = exc
            elif stdout_text.strip():
                try:
                    payload_findings = _parse_output(stdout_text)
                except Exception as exc:  # noqa: BLE001
                    parse_error = exc

            if not payload_findings and stderr_text.strip():
                try:
                    payload_findings = _parse_output(stderr_text)
                    parse_error = None
                except Exception as exc:  # noqa: BLE001
                    if parse_error is None:
                        parse_error = exc

            if parse_error is not None and not payload_findings and process_result.exit_code in {0, 1}:
                raise RuntimeError(f"bandit output parse failed: {parse_error}") from parse_error

            if process_result.exit_code > 1 and not payload_findings:
                message = (stderr_text or stdout_text or process_result.error or "unknown error").strip()
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
        finally:
            cleanup_scan_workspace("bandit-bootstrap", task_id)
