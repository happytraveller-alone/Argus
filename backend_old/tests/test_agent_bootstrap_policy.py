from types import SimpleNamespace

from app.services.agent.bootstrap_policy import (
    HYBRID_TASK_NAME_MARKER,
    INTELLIGENT_TASK_NAME_MARKER,
    _normalize_verification_level,
    _resolve_agent_task_source_mode,
    _resolve_static_bootstrap_config,
)


def test_normalize_verification_level_maps_legacy_aliases():
    assert _normalize_verification_level(None) == "analysis_with_poc_plan"
    assert _normalize_verification_level("analysis_only") == "analysis_with_poc_plan"
    assert _normalize_verification_level("sandbox") == "analysis_with_poc_plan"
    assert _normalize_verification_level("custom") == "analysis_with_poc_plan"


def test_resolve_agent_task_source_mode_prefers_markers_and_defaults_to_hybrid():
    assert (
        _resolve_agent_task_source_mode(
            f"{HYBRID_TASK_NAME_MARKER} task",
            None,
        )
        == "hybrid"
    )
    assert (
        _resolve_agent_task_source_mode(
            None,
            f"{INTELLIGENT_TASK_NAME_MARKER} desc",
        )
        == "intelligent"
    )
    assert _resolve_agent_task_source_mode(None, "混合扫描任务") == "hybrid"
    assert _resolve_agent_task_source_mode("plain task", "plain desc") == "hybrid"


def test_resolve_static_bootstrap_config_respects_source_mode_and_scope_flags():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "opengrep_enabled": False,
            }
        }
    )

    hybrid = _resolve_static_bootstrap_config(task, "hybrid")
    intelligent = _resolve_static_bootstrap_config(task, "intelligent")

    assert hybrid == {
        "mode": "embedded",
        "opengrep_enabled": False,
    }
    assert intelligent == {
        "mode": "disabled",
        "opengrep_enabled": False,
    }
