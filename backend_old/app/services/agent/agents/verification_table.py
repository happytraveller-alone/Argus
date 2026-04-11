from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FindingTableItem:
    id: str
    fingerprint: str
    title: str
    file_path: str
    line_start: int
    line_end: int
    function_name: Optional[str]
    vulnerability_type: str
    severity: str
    sources: List[str] = field(default_factory=list)

    context_status: str = "pending"  # pending|collecting|ready|failed
    verify_status: str = "unverified"  # unverified|verifying|verified|false_positive
    context_round: int = 0
    attempts: int = 0
    blocked_reason: Optional[str] = None
    context_bundle: Dict[str, Any] = field(default_factory=dict)
    verification_result: Dict[str, Any] = field(default_factory=dict)
    parent_fingerprint: Optional[str] = None
    discovered_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "title": self.title,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "function_name": self.function_name,
            "vulnerability_type": self.vulnerability_type,
            "severity": self.severity,
            "sources": list(self.sources),
            "context_status": self.context_status,
            "verify_status": self.verify_status,
            "context_round": self.context_round,
            "attempts": self.attempts,
            "blocked_reason": self.blocked_reason,
            "context_bundle": dict(self.context_bundle),
            "verification_result": dict(self.verification_result),
            "parent_fingerprint": self.parent_fingerprint,
            "discovered_by": self.discovered_by,
        }


class VerificationFindingTable:
    def __init__(self, *, max_rounds: int = 10, max_items: int = 200) -> None:
        self.max_rounds = max(1, int(max_rounds))
        self.max_items = max(1, int(max_items))
        self._items: Dict[str, FindingTableItem] = {}
        self._order: List[str] = []
        self._dedup_keys: Dict[str, str] = {}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except Exception:
            pass
        return default

    @staticmethod
    def _safe_text(value: Any, default: str = "") -> str:
        text = str(value or "").strip()
        return text if text else default

    @classmethod
    def _build_fingerprint(cls, finding: Dict[str, Any], index: int) -> str:
        file_path = cls._safe_text(finding.get("file_path") or finding.get("file"))
        line_start = cls._safe_int(finding.get("line_start") or finding.get("line"), 1)
        vuln = cls._safe_text(finding.get("vulnerability_type"), "unknown").lower()
        title = cls._safe_text(finding.get("title"), f"candidate-{index + 1}")
        raw = f"{file_path}|{line_start}|{vuln}|{title}|{index}"
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]

    @classmethod
    def _build_dedup_key(cls, finding: Dict[str, Any]) -> str:
        file_path = cls._safe_text(finding.get("file_path") or finding.get("file"))
        line_start = cls._safe_int(finding.get("line_start") or finding.get("line"), 1)
        vuln = cls._safe_text(finding.get("vulnerability_type"), "unknown").lower()
        return f"{vuln}|{file_path}|{line_start}"

    def add_candidate(
        self,
        finding: Dict[str, Any],
        *,
        source: str,
        index: int = 0,
        parent_fingerprint: Optional[str] = None,
        discovered_by: Optional[str] = None,
    ) -> Optional[FindingTableItem]:
        if not isinstance(finding, dict):
            return None
        if len(self._order) >= self.max_items:
            return None

        dedup_key = self._build_dedup_key(finding)
        existing_fp = self._dedup_keys.get(dedup_key)
        if existing_fp and existing_fp in self._items:
            existing = self._items[existing_fp]
            if source and source not in existing.sources:
                existing.sources.append(source)
            return existing

        fingerprint = self._build_fingerprint(finding, index)
        line_start = self._safe_int(finding.get("line_start") or finding.get("line"), 1)
        line_end = self._safe_int(finding.get("line_end"), line_start)
        if line_end < line_start:
            line_end = line_start

        item = FindingTableItem(
            id=f"ft-{len(self._order) + 1}-{fingerprint[:8]}",
            fingerprint=fingerprint,
            title=self._safe_text(finding.get("title"), f"候选漏洞#{len(self._order) + 1}"),
            file_path=self._safe_text(finding.get("file_path") or finding.get("file")),
            line_start=line_start,
            line_end=line_end,
            function_name=self._safe_text(finding.get("function_name") or finding.get("function")) or None,
            vulnerability_type=self._safe_text(finding.get("vulnerability_type"), "other"),
            severity=self._safe_text(finding.get("severity"), "medium"),
            sources=[source] if source else [],
            parent_fingerprint=parent_fingerprint,
            discovered_by=discovered_by,
        )
        self._items[item.fingerprint] = item
        self._order.append(item.fingerprint)
        self._dedup_keys[dedup_key] = item.fingerprint
        return item

    def get(self, fingerprint: str) -> Optional[FindingTableItem]:
        return self._items.get(str(fingerprint or "").strip())

    def iter_items(self) -> List[FindingTableItem]:
        return [self._items[fp] for fp in self._order if fp in self._items]

    def pending_context_items(self) -> List[FindingTableItem]:
        return [
            item
            for item in self.iter_items()
            if item.context_status in {"pending", "collecting"}
        ]

    def mark_context(
        self,
        fingerprint: str,
        *,
        status: str,
        context_round: Optional[int] = None,
        blocked_reason: Optional[str] = None,
        context_bundle: Optional[Dict[str, Any]] = None,
    ) -> None:
        item = self.get(fingerprint)
        if not item:
            return
        if status:
            item.context_status = status
        if context_round is not None:
            item.context_round = max(0, int(context_round))
        if blocked_reason is not None:
            item.blocked_reason = str(blocked_reason or "").strip() or None
        if isinstance(context_bundle, dict):
            item.context_bundle = dict(context_bundle)

    def mark_verify(
        self,
        fingerprint: str,
        *,
        status: str,
        attempts: Optional[int] = None,
        blocked_reason: Optional[str] = None,
        verification_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        item = self.get(fingerprint)
        if not item:
            return
        if status:
            item.verify_status = status
        if attempts is not None:
            item.attempts = max(0, int(attempts))
        if blocked_reason is not None:
            item.blocked_reason = str(blocked_reason or "").strip() or None
        if isinstance(verification_result, dict):
            item.verification_result = dict(verification_result)

    def to_todo_list(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.iter_items()]

    def summary(
        self,
        *,
        round_index: int = 0,
        queue_size: int = 0,
        newly_discovered_count: int = 0,
    ) -> Dict[str, Any]:
        items = self.iter_items()
        context_pending = len([i for i in items if i.context_status == "pending"])
        context_collecting = len([i for i in items if i.context_status == "collecting"])
        context_ready = len([i for i in items if i.context_status == "ready"])
        context_failed = len([i for i in items if i.context_status == "failed"])
        verify_unverified = len([i for i in items if i.verify_status == "unverified"])
        verify_verifying = len([i for i in items if i.verify_status == "verifying"])
        verified = len([i for i in items if i.verify_status == "verified"])
        false_positive = len([i for i in items if i.verify_status == "false_positive"])

        return {
            "total": len(items),
            "context_pending": context_pending + context_collecting,
            "context_ready": context_ready,
            "context_failed": context_failed,
            "verify_unverified": verify_unverified,
            "verify_verifying": verify_verifying,
            "verified": verified,
            "false_positive": false_positive,
            "round": max(0, int(round_index)),
            "queue_size": max(0, int(queue_size)),
            "newly_discovered_count": max(0, int(newly_discovered_count)),
        }


__all__ = ["FindingTableItem", "VerificationFindingTable"]
