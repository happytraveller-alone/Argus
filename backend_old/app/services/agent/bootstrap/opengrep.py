from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml

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
from app.db.static_finding_paths import normalize_static_scan_file_path
from app.models.opengrep import OpengrepRule
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


def _extract_rule_lookup_keys(check_id: Any) -> List[str]:
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    keys: List[str] = []

    def _append(candidate: str) -> None:
        text = str(candidate or "").strip()
        if text and text not in keys:
            keys.append(text)

    _append(raw_check_id)
    if "." in raw_check_id:
        _append(raw_check_id.rsplit(".", 1)[-1])
    return keys


def _extract_payload_confidence(rule_data: Any) -> Optional[str]:
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = _normalize_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = _normalize_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            metadata_confidence = _normalize_confidence(extra_metadata.get("confidence"))
            if metadata_confidence:
                return metadata_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = _normalize_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    return None


def _build_confidence_map(active_rules: List[OpengrepRule]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for rule in active_rules:
        normalized_confidence = _normalize_confidence(getattr(rule, "confidence", None))
        if not normalized_confidence:
            continue
        lookup_values = [getattr(rule, "id", None), getattr(rule, "name", None)]
        for raw in lookup_values:
            for key in _extract_rule_lookup_keys(raw):
                mapping[key] = normalized_confidence
    return mapping


def _parse_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []

    output = json.loads(stdout)
    if isinstance(output, dict):
        results = output.get("results", [])
    elif isinstance(output, list):
        results = output
    else:
        raise ValueError("Unexpected opengrep output type")

    if not isinstance(results, list):
        raise ValueError("Invalid opengrep results format")

    parsed: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


class OpenGrepBootstrapScanner(StaticBootstrapScanner):
    """OpenGrep 预扫实现。"""

    scanner_name = "opengrep"
    source = "opengrep_bootstrap"

    def __init__(
        self,
        *,
        active_rules: List[OpengrepRule],
        timeout_seconds: int = 900,
    ) -> None:
        self.active_rules = list(active_rules or [])
        self.timeout_seconds = max(1, int(timeout_seconds))

    def _build_merged_rules(self) -> List[Dict[str, Any]]:
        merged_rules: List[Dict[str, Any]] = []
        for rule in self.active_rules:
            try:
                parsed_yaml = yaml.safe_load(rule.pattern_yaml)
            except Exception:
                continue
            if not isinstance(parsed_yaml, dict):
                continue
            rule_items = parsed_yaml.get("rules")
            if not isinstance(rule_items, list):
                continue
            for item in rule_items:
                if isinstance(item, dict):
                    merged_rules.append(item)
        return merged_rules

    def _normalize_findings(
        self,
        payload_findings: List[Dict[str, Any]],
    ) -> List[StaticBootstrapFinding]:
        confidence_map = _build_confidence_map(self.active_rules)
        normalized: List[StaticBootstrapFinding] = []

        for index, payload in enumerate(payload_findings):
            check_id = payload.get("check_id") or payload.get("id")
            confidence = _extract_payload_confidence(payload)
            if confidence is None:
                for key in _extract_rule_lookup_keys(check_id):
                    mapped = confidence_map.get(key)
                    if mapped:
                        confidence = mapped
                        break

            extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
            title = extra.get("message") or str(check_id or "OpenGrep 发现")
            description = extra.get("message") or ""
            file_path = normalize_static_scan_file_path(
                str(payload.get("path") or "").strip(),
                "/scan/project",
            )
            start_obj = payload.get("start")
            end_obj = payload.get("end")
            start_line = int(start_obj.get("line") or 0) if isinstance(start_obj, dict) else 0
            end_line = int(end_obj.get("line") or start_line) if isinstance(end_obj, dict) else start_line
            severity_text = str(extra.get("severity") or "INFO").strip().upper()
            code_snippet = extra.get("lines")

            normalized.append(
                StaticBootstrapFinding(
                    id=str(check_id or f"opengrep-{index}"),
                    title=str(title),
                    description=str(description),
                    file_path=file_path,
                    line_start=start_line or None,
                    line_end=end_line or None,
                    code_snippet=str(code_snippet) if code_snippet is not None else None,
                    severity=severity_text,
                    confidence=confidence,
                    vulnerability_type=str(check_id or "opengrep_rule"),
                    source=self.source,
                )
            )
        return normalized

    async def scan(self, project_root: str) -> StaticBootstrapScanResult:
        merged_rules = self._build_merged_rules()
        if not merged_rules:
            raise ValueError("No executable opengrep rules found")

        task_id = f"bootstrap-{uuid4().hex}"
        workspace_dir = ensure_scan_workspace("opengrep-bootstrap", task_id)
        project_dir = ensure_scan_project_dir("opengrep-bootstrap", task_id)
        output_dir = ensure_scan_output_dir("opengrep-bootstrap", task_id)
        logs_dir = ensure_scan_logs_dir("opengrep-bootstrap", task_id)
        meta_dir = ensure_scan_meta_dir("opengrep-bootstrap", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        merged_rule_path: Optional[str] = None
        report_file = output_dir / "report.json"

        try:
            await asyncio.to_thread(shutil.rmtree, project_dir, True)
            await asyncio.to_thread(copy_project_tree_to_scan_dir, project_root, project_dir)

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".yml",
                dir=str(meta_dir),
                delete=False,
            ) as temp_file:
                yaml.dump(
                    {"rules": merged_rules},
                    temp_file,
                    sort_keys=False,
                    default_flow_style=False,
                )
                merged_rule_path = temp_file.name

            runner_rule_path = str(Path("/scan/meta") / Path(merged_rule_path).name)
            cmd = ["opengrep", "--config", runner_rule_path, "--json", "/scan/project"]
            if report_file.exists():
                report_file.unlink()
            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="opengrep-bootstrap",
                    image=str(
                        getattr(settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:latest")
                    ),
                    workspace_dir=str(workspace_dir),
                    command=cmd,
                    timeout_seconds=self.timeout_seconds,
                    env={
                        "NO_PROXY": "*",
                        "no_proxy": "*",
                    },
                    artifact_paths=["output/report.json"],
                    capture_stdout_path="output/report.json",
                )
            )

            stderr_text = ""
            stdout_text = report_file.read_text(encoding="utf-8", errors="ignore") if report_file.exists() else ""
            if process_result.stderr_path and Path(process_result.stderr_path).exists():
                stderr_text = Path(process_result.stderr_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            payload_findings = _parse_output(stdout_text)
            if process_result.exit_code != 0 and not payload_findings:
                stderr_message = (stderr_text or stdout_text or process_result.error or "unknown error").strip()
                raise RuntimeError(f"opengrep failed: {stderr_message[:300]}")

            findings = self._normalize_findings(payload_findings)
            return StaticBootstrapScanResult(
                scanner_name=self.scanner_name,
                source=self.source,
                total_findings=len(payload_findings),
                findings=findings,
                metadata={
                    "rules_count": len(self.active_rules),
                    "merged_rules_count": len(merged_rules),
                    "timeout_seconds": self.timeout_seconds,
                },
            )
        finally:
            if merged_rule_path:
                try:
                    os.unlink(merged_rule_path)
                except Exception:
                    pass
            cleanup_scan_workspace("opengrep-bootstrap", task_id)
