from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

import yaml

from app.models.opengrep import OpengrepRule

from .base import (
    StaticBootstrapFinding,
    StaticBootstrapScanResult,
    StaticBootstrapScanner,
)


def _ensure_opengrep_xdg_dirs() -> None:
    """确保 XDG 目录存在，防止 opengrep (Semgrep) 因缺少 XDG_CONFIG_HOME 等目录而启动失败。"""
    for env_key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        path = os.environ.get(env_key, "")
        if path and not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError:
                pass


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
            file_path = str(payload.get("path") or "").strip()
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

        _ensure_opengrep_xdg_dirs()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as temp_file:
            yaml.dump({"rules": merged_rules}, temp_file, sort_keys=False, default_flow_style=False)
            merged_rule_path = temp_file.name

        try:
            cmd = ["opengrep", "--config", merged_rule_path, "--json", project_root]
            process_result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            payload_findings = _parse_output(process_result.stdout or "")
            if process_result.returncode != 0 and not payload_findings:
                stderr_text = (process_result.stderr or process_result.stdout or "unknown error").strip()
                raise RuntimeError(f"opengrep failed: {stderr_text[:300]}")

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
            try:
                os.unlink(merged_rule_path)
            except Exception:
                pass
