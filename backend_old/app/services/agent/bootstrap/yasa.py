"""YASA hybrid bootstrap scanner."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.api.v1.endpoints.static_tasks_shared import (
    cleanup_scan_workspace,
    copy_project_tree_to_scan_dir,
    ensure_scan_logs_dir,
    ensure_scan_output_dir,
    ensure_scan_project_dir,
    ensure_scan_workspace,
)
from app.core.config import settings
from app.models.yasa import YasaRuleConfig
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container
from app.services.yasa_runtime import (
    YASA_RUNNER_BINARY,
    YASA_RUNNER_RESOURCE_DIR,
    build_yasa_rule_config_path,
    build_yasa_scan_command,
)
from app.services.yasa_language import resolve_yasa_language_profile

from .base import StaticBootstrapFinding, StaticBootstrapScanResult, StaticBootstrapScanner


def _parse_sarif(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return []

    findings: List[Dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            message_payload = item.get("message")
            if isinstance(message_payload, dict):
                message = str(message_payload.get("text") or "").strip()
            else:
                message = ""

            first_location = None
            locations = item.get("locations")
            if isinstance(locations, list) and locations:
                first_location = locations[0] if isinstance(locations[0], dict) else None
            physical_location = (
                first_location.get("physicalLocation")
                if isinstance(first_location, dict)
                else None
            )
            artifact = (
                physical_location.get("artifactLocation")
                if isinstance(physical_location, dict)
                else None
            )
            region = (
                physical_location.get("region")
                if isinstance(physical_location, dict)
                else None
            )
            file_path = str((artifact or {}).get("uri") or "").strip() or "unknown"
            start_line = region.get("startLine") if isinstance(region, dict) else None
            end_line = region.get("endLine") if isinstance(region, dict) else None
            if not isinstance(start_line, int):
                start_line = None
            if not isinstance(end_line, int):
                end_line = None

            rule_id = str(item.get("ruleId") or "").strip() or "yasa_rule"
            level = str(item.get("level") or "warning").strip().upper() or "WARNING"

            findings.append(
                {
                    "rule_id": rule_id,
                    "message": message or rule_id,
                    "file_path": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "level": level,
                }
            )
    return findings


class YasaBootstrapScanner(StaticBootstrapScanner):
    scanner_name = "yasa"
    source = "yasa_bootstrap"

    def __init__(
        self,
        *,
        language: str = "python",
        timeout_seconds: Optional[int] = None,
        custom_rule_config: Optional[YasaRuleConfig] = None,
    ):
        normalized = str(language or "").strip().lower() or "python"
        if normalized in {"javascript", "js"}:
            normalized = "typescript"
        self.profile = resolve_yasa_language_profile(normalized)
        configured_timeout = int(getattr(settings, "YASA_TIMEOUT_SECONDS", 600) or 600)
        self.timeout_seconds = max(1, int(timeout_seconds or configured_timeout))
        self.custom_rule_config = custom_rule_config

    def _build_rule_config(self) -> Optional[str]:
        try:
            return build_yasa_rule_config_path(
                self.profile["rule_config"],
                resource_dir=YASA_RUNNER_RESOURCE_DIR,
            )
        except Exception:
            return None

    def _normalize_findings(self, findings: List[Dict[str, Any]]) -> List[StaticBootstrapFinding]:
        normalized: List[StaticBootstrapFinding] = []
        for idx, item in enumerate(findings):
            level = str(item.get("level") or "WARNING").upper()
            severity = "ERROR" if level in {"ERROR", "CRITICAL"} else "WARNING"
            normalized.append(
                StaticBootstrapFinding(
                    id=f"yasa-{idx}",
                    title=str(item.get("rule_id") or "yasa_rule"),
                    description=str(item.get("message") or "yasa finding"),
                    file_path=str(item.get("file_path") or "unknown"),
                    line_start=item.get("start_line") if isinstance(item.get("start_line"), int) else None,
                    line_end=item.get("end_line") if isinstance(item.get("end_line"), int) else None,
                    code_snippet=None,
                    severity=severity,
                    confidence="MEDIUM",
                    vulnerability_type=str(item.get("rule_id") or "yasa_rule"),
                    source=self.source,
                    extra={"yasa_level": level},
                )
            )
        return normalized

    async def scan(self, project_root: str) -> StaticBootstrapScanResult:
        if not bool(getattr(settings, "YASA_ENABLED", True)):
            return StaticBootstrapScanResult(
                scanner_name=self.scanner_name,
                source=self.source,
                total_findings=0,
                findings=[],
                metadata={"enabled": False},
            )

        rule_config_file = self._build_rule_config()
        task_id = f"bootstrap-{uuid4().hex}"
        workspace_dir = ensure_scan_workspace("yasa-bootstrap", task_id)
        project_dir = ensure_scan_project_dir("yasa-bootstrap", task_id)
        output_dir = ensure_scan_output_dir("yasa-bootstrap", task_id)
        ensure_scan_logs_dir("yasa-bootstrap", task_id)
        meta_dir = Path(workspace_dir) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.rmtree, project_dir, True)
        await asyncio.to_thread(copy_project_tree_to_scan_dir, project_root, project_dir)
        checker_pack_ids = [self.profile["checker_pack"]]
        checker_ids: List[str] | None = None
        if self.custom_rule_config is not None:
            checker_pack_ids = [
                item.strip()
                for item in str(self.custom_rule_config.checker_pack_ids or "").split(",")
                if item.strip()
            ]
            checker_ids = [
                item.strip()
                for item in str(self.custom_rule_config.checker_ids or "").split(",")
                if item.strip()
            ] or None
            staged_rule_config = meta_dir / "custom-rule-config.json"
            staged_rule_config.write_text(
                str(self.custom_rule_config.rule_config_json or ""),
                encoding="utf-8",
            )
            rule_config_file = str(Path("/scan/meta") / staged_rule_config.name)
        cmd = build_yasa_scan_command(
            binary=YASA_RUNNER_BINARY,
            source_path="/scan/project",
            language=self.profile["language"],
            report_dir="/scan/output",
            checker_pack_ids=checker_pack_ids,
            checker_ids=checker_ids,
            rule_config_file=rule_config_file,
            use_runner_paths=True,
        )

        try:
            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="yasa-bootstrap",
                    image=str(getattr(settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:latest")),
                    workspace_dir=str(workspace_dir),
                    command=cmd,
                    timeout_seconds=self.timeout_seconds,
                    env={"YASA_RESOURCE_DIR": YASA_RUNNER_RESOURCE_DIR},
                )
            )
            sarif_path = output_dir / "report.sarif"
            findings: List[Dict[str, Any]] = []
            if sarif_path.exists():
                try:
                    payload = json.loads(sarif_path.read_text(encoding="utf-8", errors="ignore"))
                    findings = _parse_sarif(payload)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"yasa output parse failed: {exc}") from exc

            if (not process_result.success or process_result.exit_code != 0) and not findings:
                raise RuntimeError(
                    f"yasa failed: {str(process_result.error or 'unknown error')[:300]}"
                )

            normalized = self._normalize_findings(findings)
            return StaticBootstrapScanResult(
                scanner_name=self.scanner_name,
                source=self.source,
                total_findings=len(findings),
                findings=normalized,
                metadata={
                    "language": self.profile["language"],
                    "checker_pack": self.profile["checker_pack"],
                },
            )
        finally:
            cleanup_scan_workspace("yasa-bootstrap", task_id)
