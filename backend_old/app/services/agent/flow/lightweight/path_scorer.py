from __future__ import annotations

from typing import Any, Dict, List

from app.services.agent.flow.models import FlowEvidence


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_path_score(
    *,
    path_found: bool,
    call_chain: List[str],
    control_conditions: List[str],
    entry_inferred: bool,
    blocked_reasons: List[str],
    has_code2flow: bool,
) -> float:
    score = 0.2

    if path_found:
        score += 0.45
    if call_chain:
        score += min(0.2, max(len(call_chain) - 1, 0) * 0.03)
    if control_conditions:
        score += min(0.12, len(control_conditions) * 0.02)
    if has_code2flow:
        score += 0.08

    if entry_inferred:
        score -= 0.05
    if blocked_reasons:
        score -= min(0.15, len(blocked_reasons) * 0.03)

    return clamp_score(score)


def build_lightweight_flow_evidence(
    path_result: Dict[str, Any],
    *,
    has_code2flow: bool,
) -> FlowEvidence:
    call_chain = [str(item) for item in (path_result.get("call_chain") or []) if str(item).strip()]
    control_conditions = [
        str(item) for item in (path_result.get("control_conditions") or []) if str(item).strip()
    ]
    blocked_reasons = [
        str(item) for item in (path_result.get("blocked_reasons") or []) if str(item).strip()
    ]
    entry_inferred = bool(path_result.get("entry_inferred"))
    path_found = bool(path_result.get("path_found"))

    taint_paths: List[str] = []
    if len(call_chain) >= 2:
        for idx in range(len(call_chain) - 1):
            taint_paths.append(f"{call_chain[idx]} -> {call_chain[idx + 1]}")

    path_score = compute_path_score(
        path_found=path_found,
        call_chain=call_chain,
        control_conditions=control_conditions,
        entry_inferred=entry_inferred,
        blocked_reasons=blocked_reasons,
        has_code2flow=has_code2flow,
    )

    return FlowEvidence(
        path_found=path_found,
        path_score=path_score,
        call_chain=call_chain,
        control_conditions=control_conditions,
        taint_paths=taint_paths,
        entry_inferred=entry_inferred,
        blocked_reasons=blocked_reasons,
        engine="ts_code2flow",
        extra={"code2flow_enabled": bool(has_code2flow)},
    )


__all__ = ["build_lightweight_flow_evidence", "compute_path_score", "clamp_score"]
