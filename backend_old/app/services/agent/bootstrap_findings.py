"""Bootstrap finding parsing and normalization helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent.scope_filters import _normalize_bootstrap_confidence
from app.services.scan_path_utils import normalize_scan_file_path


def _extract_bootstrap_rule_lookup_keys(check_id: Any) -> List[str]:
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    keys: List[str] = []

    def _append(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in keys:
            keys.append(normalized)

    _append(raw_check_id)
    if "." in raw_check_id:
        _append(raw_check_id.rsplit(".", 1)[-1])
    return keys


def _extract_bootstrap_payload_confidence(rule_data: Any) -> Optional[str]:
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = _normalize_bootstrap_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = _normalize_bootstrap_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            metadata_confidence = _normalize_bootstrap_confidence(
                extra_metadata.get("confidence")
            )
            if metadata_confidence:
                return metadata_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = _normalize_bootstrap_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    return None


def _parse_bootstrap_opengrep_output(stdout: str) -> List[Dict[str, Any]]:
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

    return [item for item in results if isinstance(item, dict)]


def _build_bootstrap_confidence_map_from_rules(
    rules: List[Any],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for rule in rules:
        normalized_confidence = _normalize_bootstrap_confidence(
            getattr(rule, "confidence", None)
        )
        if not normalized_confidence:
            continue
        lookup_values = [getattr(rule, "id", None), getattr(rule, "name", None)]
        for raw_value in lookup_values:
            for key in _extract_bootstrap_rule_lookup_keys(raw_value):
                mapping[key] = normalized_confidence
    return mapping


def _normalize_bootstrap_finding_from_opengrep_payload(
    finding: Dict[str, Any],
    confidence_map: Dict[str, str],
    index: int,
) -> Dict[str, Any]:
    rule_data = finding if isinstance(finding, dict) else {}
    check_id = rule_data.get("check_id") or rule_data.get("id")

    confidence = _extract_bootstrap_payload_confidence(rule_data)
    if confidence is None:
        for key in _extract_bootstrap_rule_lookup_keys(check_id):
            mapped = confidence_map.get(key)
            if mapped:
                confidence = mapped
                break

    extra = rule_data.get("extra") if isinstance(rule_data.get("extra"), dict) else {}
    title = extra.get("message") or str(check_id or "OpenGrep 发现")
    description = extra.get("message") or ""
    file_path = str(rule_data.get("path") or "").strip()
    start_obj = rule_data.get("start")
    end_obj = rule_data.get("end")
    start_line = int(start_obj.get("line") or 0) if isinstance(start_obj, dict) else 0
    end_line = (
        int(end_obj.get("line") or start_line)
        if isinstance(end_obj, dict)
        else start_line
    )
    severity_text = str(extra.get("severity") or "INFO").strip().upper()
    code_snippet = extra.get("lines")

    return {
        "id": str(check_id or f"opengrep-{index}"),
        "title": str(title),
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": severity_text,
        "confidence": confidence,
        "vulnerability_type": str(check_id or "opengrep_rule"),
        "source": "opengrep_bootstrap",
    }


def _normalize_bootstrap_finding_from_gitleaks_payload(
    finding: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    rule_id = str(finding.get("RuleID") or "gitleaks_secret").strip()
    description = str(finding.get("Description") or "Gitleaks 密钥泄露候选").strip()
    file_path = normalize_scan_file_path(
        str(finding.get("File") or "").strip(),
        "/scan/project",
    )
    start_line = int(finding.get("StartLine") or 0)
    end_line = int(finding.get("EndLine") or start_line)
    code_snippet = finding.get("Match") or finding.get("Secret")
    title = f"Gitleaks: {rule_id}" if rule_id else "Gitleaks 密钥泄露候选"

    return {
        "id": f"gitleaks-{index}",
        "title": title,
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": "ERROR",
        "confidence": "HIGH",
        "vulnerability_type": rule_id or "gitleaks_secret",
        "source": "gitleaks_bootstrap",
    }


def _parse_bootstrap_gitleaks_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []
    output = json.loads(stdout)
    if isinstance(output, list):
        return [item for item in output if isinstance(item, dict)]
    if isinstance(output, dict):
        nested = output.get("findings")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    raise ValueError("Unexpected gitleaks output type")


def _dedupe_bootstrap_findings(
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[Tuple[str, int, str, str]] = set()
    for item in findings:
        file_path = str(item.get("file_path") or "").strip()
        line_start = int(item.get("line_start") or 0)
        vuln_type = str(item.get("vulnerability_type") or "").strip()
        source = str(item.get("source") or "").strip()
        key = (file_path, line_start, vuln_type, source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
