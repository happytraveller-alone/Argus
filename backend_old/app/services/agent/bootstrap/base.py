from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StaticBootstrapFinding:
    """统一的静态预扫候选输出。"""

    id: str
    title: str
    description: str
    file_path: str
    line_start: Optional[int]
    line_end: Optional[int]
    code_snippet: Optional[str]
    severity: str
    confidence: Optional[str]
    vulnerability_type: str
    source: str
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        extra_payload = payload.pop("extra", {}) or {}
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        return payload


@dataclass
class StaticBootstrapScanResult:
    """统一的静态预扫扫描结果。"""

    scanner_name: str
    source: str
    total_findings: int
    findings: List[StaticBootstrapFinding]
    metadata: Dict[str, Any] = field(default_factory=dict)


class StaticBootstrapScanner(ABC):
    """静态预扫工具抽象基类。"""

    scanner_name: str = "unknown"
    source: str = "unknown_bootstrap"

    @abstractmethod
    async def scan(self, project_root: str) -> StaticBootstrapScanResult:
        """执行扫描并返回统一结构的结果。"""
        raise NotImplementedError
