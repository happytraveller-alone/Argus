"""Bootstrap policy helpers shared by legacy agent task modules."""

from __future__ import annotations

from typing import Any, Dict, Optional


_VERIFICATION_LEVEL_ALIASES = {
    "analysis_with_poc_plan": "analysis_with_poc_plan",
    "analysis_only": "analysis_with_poc_plan",
    "sandbox": "analysis_with_poc_plan",
    "generate_poc": "analysis_with_poc_plan",
    "poc_plan": "analysis_with_poc_plan",
}

HYBRID_TASK_NAME_MARKER = "[HYBRID]"
INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]"


def _normalize_verification_level(value: Optional[str]) -> str:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return "analysis_with_poc_plan"
    return _VERIFICATION_LEVEL_ALIASES.get(raw_value, "analysis_with_poc_plan")


def _resolve_agent_task_source_mode(
    name: Optional[str],
    description: Optional[str],
) -> str:
    normalized_name = str(name or "").strip().lower()
    normalized_description = str(description or "").strip().lower()
    normalized_combined = f"{normalized_name} {normalized_description}"
    if (
        HYBRID_TASK_NAME_MARKER.lower() in normalized_combined
        or "混合扫描" in normalized_combined
    ):
        return "hybrid"
    if INTELLIGENT_TASK_NAME_MARKER.lower() in normalized_combined:
        return "intelligent"
    return "hybrid"


def _resolve_static_bootstrap_config(
    task: Any,
    source_mode: str,
) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "mode": "disabled",
        "opengrep_enabled": False,
    }
    if source_mode == "hybrid":
        defaults = {
            "mode": "embedded",
            "opengrep_enabled": True,
        }

    audit_scope = task.audit_scope if isinstance(getattr(task, "audit_scope", None), dict) else {}
    static_bootstrap = (
        audit_scope.get("static_bootstrap")
        if isinstance(audit_scope.get("static_bootstrap"), dict)
        else {}
    )

    raw_mode = str(static_bootstrap.get("mode") or defaults["mode"]).strip().lower()
    mode = "embedded" if raw_mode == "embedded" else "disabled"
    if source_mode != "hybrid":
        mode = "disabled"

    opengrep_enabled = bool(
        static_bootstrap.get("opengrep_enabled", defaults["opengrep_enabled"])
    )

    if mode == "disabled":
        opengrep_enabled = False

    return {
        "mode": mode,
        "opengrep_enabled": opengrep_enabled,
    }
