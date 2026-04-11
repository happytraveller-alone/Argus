"""Core audit scope filtering helpers shared by legacy agent task modules."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


_CORE_AUDIT_EXCLUDE_PATTERNS: List[str] = [
    "test/**",
    "tests/**",
    "**/test/**",
    "**/tests/**",
    ".*/**",
    "**/.*/**",
    "*config*.*",
    "**/*config*.*",
    "*settings*.*",
    "**/*settings*.*",
    ".env*",
    "**/.env*",
    "*.yml",
    "**/*.yml",
    "*.yaml",
    "**/*.yaml",
    "*.json",
    "**/*.json",
    "*.ini",
    "**/*.ini",
    "*.conf",
    "**/*.conf",
    "*.toml",
    "**/*.toml",
    "*.properties",
    "**/*.properties",
    "*.plist",
    "**/*.plist",
    "*.xml",
    "**/*.xml",
]


def _normalize_bootstrap_confidence(confidence: Any) -> Optional[str]:
    normalized = str(confidence or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _build_core_audit_exclude_patterns(
    user_patterns: Optional[List[str]],
) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    raw_patterns = list(user_patterns or []) + _CORE_AUDIT_EXCLUDE_PATTERNS
    for raw in raw_patterns:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip().replace("\\", "/")
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(normalized)
    return merged


def _normalize_scan_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _path_components(path: str) -> List[str]:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return []
    return [part for part in normalized.split("/") if part not in {"", ".", ".."}]


def _match_exclude_patterns(path: str, patterns: Optional[List[str]]) -> bool:
    import fnmatch

    normalized = _normalize_scan_path(path)
    basename = os.path.basename(normalized)
    for pattern in patterns or []:
        if not isinstance(pattern, str):
            continue
        candidate = pattern.strip().replace("\\", "/")
        if not candidate:
            continue
        if fnmatch.fnmatch(normalized, candidate) or fnmatch.fnmatch(basename, candidate):
            return True
    return False


def _is_core_ignored_path(
    path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> bool:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return False

    parts = _path_components(normalized)
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in {"test", "tests"}:
            return True
        if part.startswith("."):
            return True

    if parts:
        last = parts[-1]
        if last.lower() in {"test", "tests"}:
            return True
        if last.startswith("."):
            return True

    effective_patterns = _build_core_audit_exclude_patterns(exclude_patterns)
    if _match_exclude_patterns(normalized, effective_patterns):
        return True

    return False


def _filter_bootstrap_findings(
    normalized_findings: List[Dict[str, Any]],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in normalized_findings:
        file_path = str(item.get("file_path") or "").strip()
        if file_path and _is_core_ignored_path(file_path, exclude_patterns):
            continue
        severity_value = str(item.get("severity") or "").upper()
        confidence_value = _normalize_bootstrap_confidence(item.get("confidence"))
        if severity_value != "ERROR":
            continue
        if confidence_value not in {"HIGH", "MEDIUM"}:
            continue
        copied = dict(item)
        copied["confidence"] = confidence_value
        filtered.append(copied)
    return filtered
