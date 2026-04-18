from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


FlowEngine = Literal["ts_code2flow", "logic_graph"]


@dataclass
class FlowEvidence:
    """Unified flow evidence payload for reachability reasoning."""

    path_found: bool = False
    path_score: float = 0.0
    call_chain: List[str] = field(default_factory=list)
    control_conditions: List[str] = field(default_factory=list)
    taint_paths: List[str] = field(default_factory=list)
    entry_inferred: bool = False
    blocked_reasons: List[str] = field(default_factory=list)
    engine: FlowEngine = "ts_code2flow"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_found": bool(self.path_found),
            "path_score": float(max(0.0, min(self.path_score, 1.0))),
            "call_chain": list(self.call_chain),
            "control_conditions": list(self.control_conditions),
            "taint_paths": list(self.taint_paths),
            "entry_inferred": bool(self.entry_inferred),
            "blocked_reasons": list(self.blocked_reasons),
            "engine": self.engine,
            **(self.extra or {}),
        }


def merge_flow_evidence(primary: FlowEvidence, fallback: FlowEvidence) -> FlowEvidence:
    """Prefer higher confidence evidence while preserving diagnostics."""
    winner = primary if primary.path_score >= fallback.path_score else fallback
    loser = fallback if winner is primary else primary

    merged = FlowEvidence(
        path_found=winner.path_found or loser.path_found,
        path_score=max(winner.path_score, loser.path_score),
        call_chain=winner.call_chain or loser.call_chain,
        control_conditions=winner.control_conditions or loser.control_conditions,
        taint_paths=winner.taint_paths or loser.taint_paths,
        entry_inferred=winner.entry_inferred or loser.entry_inferred,
        blocked_reasons=list(dict.fromkeys((winner.blocked_reasons or []) + (loser.blocked_reasons or []))),
        engine=winner.engine,
        extra={**(loser.extra or {}), **(winner.extra or {})},
    )
    return merged
