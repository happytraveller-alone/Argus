"""Bootstrap seed normalization and merge helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


MAX_SEED_FINDINGS = 25


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_seed_from_opengrep(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 OpenGrep bootstrap 候选统一转换为 fixed-first 的 seed findings 格式。"""

    def map_severity(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if raw == "ERROR":
            return "high"
        if raw == "WARNING":
            return "medium"
        if raw == "INFO":
            return "low"
        return "medium"

    def map_confidence(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        raw = str(value or "").strip().upper()
        if raw == "HIGH":
            return 0.8
        if raw == "MEDIUM":
            return 0.7
        if raw == "LOW":
            return 0.4
        try:
            return max(0.0, min(float(raw), 1.0))
        except Exception:
            return 0.5

    seeds: List[Dict[str, Any]] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or item.get("path") or "").strip()
        line_start = _to_int(item.get("line_start")) or _to_int(item.get("line")) or 1
        line_end = _to_int(item.get("line_end")) or line_start
        vuln_type = str(item.get("vulnerability_type") or item.get("check_id") or "opengrep_rule").strip()

        title = item.get("title") or item.get("description") or "OpenGrep 发现"
        description = item.get("description") or ""
        code_snippet = item.get("code_snippet") or item.get("code") or ""

        raw_severity = item.get("severity") or item.get("extra", {}).get("severity")
        raw_confidence = item.get("confidence")

        seeds.append(
            {
                "id": item.get("id"),
                "title": str(title).strip() if title is not None else "OpenGrep 发现",
                "description": str(description).strip(),
                "file_path": file_path,
                "line_start": int(line_start),
                "line_end": int(line_end),
                "code_snippet": str(code_snippet)[:2000],
                "severity": map_severity(raw_severity),
                "confidence": map_confidence(raw_confidence),
                "vulnerability_type": vuln_type or "opengrep_rule",
                "source": str(item.get("source") or "opengrep_bootstrap"),
                "needs_verification": True,
                "bootstrap_severity": str(raw_severity or "").strip(),
                "bootstrap_confidence": str(raw_confidence or "").strip(),
            }
        )

    seen: set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(key=lambda s: (-float(s.get("confidence") or 0.0), str(s.get("file_path") or "")))
    return deduped[:MAX_SEED_FINDINGS]


def _merge_seed_and_agent_findings(
    seed_findings: List[Dict[str, Any]],
    agent_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    seed_findings = [f for f in (seed_findings or []) if isinstance(f, dict)]
    agent_findings = [f for f in (agent_findings or []) if isinstance(f, dict)]

    def key_for(f: Dict[str, Any]) -> Tuple[str, int, str]:
        file_path = str(f.get("file_path") or "").replace("\\", "/").strip()
        line_start = _to_int(f.get("line_start")) or _to_int(f.get("line")) or 0
        vuln_type = str(f.get("vulnerability_type") or "").strip().lower()
        title = str(f.get("title") or "").strip().lower()
        if file_path and line_start and vuln_type:
            return (file_path, int(line_start), vuln_type)
        return (file_path, int(line_start), title)

    seed_by_key: Dict[Tuple[str, int, str], Dict[str, Any]] = {key_for(f): f for f in seed_findings}
    merged: List[Dict[str, Any]] = []
    for finding in agent_findings:
        key = key_for(finding)
        seed = seed_by_key.get(key)
        if seed:
            merged.append({**seed, **finding})
        else:
            merged.append(finding)

    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, int, str]] = set()
    for finding in merged:
        key = key_for(finding)
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out
