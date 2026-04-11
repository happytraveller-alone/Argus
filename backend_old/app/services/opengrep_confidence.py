"""Shared helpers for Opengrep confidence normalization and aggregation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.opengrep import OpengrepFinding, OpengrepRule


def normalize_confidence(confidence: Any) -> Optional[str]:
    """Normalize confidence to HIGH/MEDIUM/LOW."""
    normalized = str(confidence or "").strip().upper()
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "MEDIUM":
        return "MEDIUM"
    if normalized == "LOW":
        return "LOW"
    return None


def extract_rule_lookup_keys(check_id: Any) -> List[str]:
    """
    Extract lookup candidates for matching OpengrepRule.name.

    Example:
    - "python.security.sql-injection" ->
      ["python.security.sql-injection", "sql-injection"]
    """
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    def _strip_runtime_prefix(value: str) -> str:
        return re.sub(
            r"^(?:tmp[-_]+|tem[-_]+)+",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()

    keys: List[str] = []

    def _append(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in keys:
            keys.append(normalized)

    cleaned_check_id = _strip_runtime_prefix(raw_check_id)
    _append(raw_check_id)
    _append(cleaned_check_id)

    for candidate in (raw_check_id, cleaned_check_id):
        if "." in candidate:
            suffix = candidate.rsplit(".", 1)[-1].strip()
            cleaned_suffix = _strip_runtime_prefix(suffix)
            _append(suffix)
            _append(cleaned_suffix)

    return keys


def extract_finding_payload_confidence(rule_data: Any) -> Optional[str]:
    """
    Read confidence from finding.rule payload.

    Supported keys:
    - finding.rule.confidence
    - finding.rule.extra.confidence
    - finding.rule.metadata.confidence
    - finding.rule.extra.metadata.confidence
    """
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = normalize_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = normalize_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = normalize_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    if isinstance(extra, dict):
        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            return normalize_confidence(extra_metadata.get("confidence"))

    return None


def build_rule_confidence_map(
    rows: Sequence[Sequence[Any]],
) -> Dict[str, Optional[str]]:
    """Build lookup map: rule-name-candidate -> normalized confidence."""
    rule_confidence_map: Dict[str, Optional[str]] = {}
    for row in rows:
        rule_name = row[0] if len(row) > 0 else None
        rule_confidence = row[1] if len(row) > 1 else None
        normalized_rule_name = str(rule_name or "").strip()
        if not normalized_rule_name:
            continue

        normalized_confidence = normalize_confidence(rule_confidence)
        for lookup_key in extract_rule_lookup_keys(normalized_rule_name):
            existing = rule_confidence_map.get(lookup_key)
            if existing is None and normalized_confidence is not None:
                rule_confidence_map[lookup_key] = normalized_confidence
                continue
            if lookup_key not in rule_confidence_map:
                rule_confidence_map[lookup_key] = normalized_confidence
    return rule_confidence_map


async def count_high_confidence_findings_by_task_ids(
    db: AsyncSession,
    task_ids: List[str],
) -> Dict[str, int]:
    """
    Count HIGH-confidence findings for each scan task.

    False-positive findings are excluded.
    """
    normalized_task_ids = [
        str(task_id).strip() for task_id in task_ids if str(task_id).strip()
    ]
    if not normalized_task_ids:
        return {}

    counts = {task_id: 0 for task_id in normalized_task_ids}
    result = await db.execute(
        select(OpengrepFinding.scan_task_id, OpengrepFinding.rule).where(
            OpengrepFinding.scan_task_id.in_(normalized_task_ids),
            or_(
                OpengrepFinding.status.is_(None),
                OpengrepFinding.status != "false_positive",
            ),
        )
    )
    finding_rows = result.all()
    if not finding_rows:
        return counts

    rule_name_candidates: set[str] = set()
    for _, rule_data in finding_rows:
        if not isinstance(rule_data, dict):
            continue
        check_id = rule_data.get("check_id") or rule_data.get("id")
        for key in extract_rule_lookup_keys(check_id):
            rule_name_candidates.add(key)

    rule_confidence_map: Dict[str, Optional[str]] = {}
    if rule_name_candidates:
        rule_result = await db.execute(
            select(OpengrepRule.name, OpengrepRule.confidence).where(
                OpengrepRule.name.in_(rule_name_candidates)
            )
        )
        rule_confidence_map = build_rule_confidence_map(rule_result.all())

    for scan_task_id, rule_data in finding_rows:
        resolved_confidence = extract_finding_payload_confidence(rule_data)
        if not resolved_confidence and isinstance(rule_data, dict):
            check_id = rule_data.get("check_id") or rule_data.get("id")
            for key in extract_rule_lookup_keys(check_id):
                mapped = rule_confidence_map.get(key)
                if mapped:
                    resolved_confidence = mapped
                    break

        if resolved_confidence == "HIGH":
            task_key = str(scan_task_id)
            counts[task_key] = counts.get(task_key, 0) + 1

    return counts
