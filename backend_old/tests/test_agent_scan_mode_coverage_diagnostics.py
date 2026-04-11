from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


NON_TRANSIENT_RUNTIME_ERROR_CLASSES: Set[str] = {
    "invalid_recon_queue_service_binding",
    "invalid_callable_binding",
    "tool_route_missing",
    "tool_runtime_unavailable",
    "tool_adapter_unavailable",
    "tool_unhandled_in_strict_mode",
    "runtime_non_transient_error",
}

LIBPLIST_PROJECT_ID = "c157af04-bb37-472f-99f7-914a2a0fc558"


def build_libplist_scan_request(mode: str) -> Dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in {"intelligent", "hybrid"}:
        raise ValueError("mode must be intelligent or hybrid")
    marker = "[INTELLIGENT]" if normalized_mode == "intelligent" else "[HYBRID]"
    return {
        "project_id": LIBPLIST_PROJECT_ID,
        "name": f"{marker} libplist coverage diagnostics",
        "description": f"{normalized_mode} scan diagnostics for libplist",
        "task_type": "security_audit",
    }


def _event_get(event: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        if field_name == "metadata":
            metadata = event.get("metadata")
            if isinstance(metadata, Mapping):
                return metadata
            event_metadata = event.get("event_metadata")
            if isinstance(event_metadata, Mapping):
                return event_metadata
            return default
        return event.get(field_name, default)
    if field_name == "metadata":
        metadata = getattr(event, "metadata", None)
        if isinstance(metadata, Mapping):
            return metadata
        event_metadata = getattr(event, "event_metadata", None)
        if isinstance(event_metadata, Mapping):
            return event_metadata
        return default
    return getattr(event, field_name, default)


def _tool_output_text(event: Any) -> str:
    tool_output = _event_get(event, "tool_output", None)
    if isinstance(tool_output, Mapping):
        return str(tool_output.get("result") or "")
    return ""


def build_scan_mode_coverage_matrix(
    events: Sequence[Any],
    *,
    available_tools: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    available_set: Set[str] = {
        str(name).strip()
        for name in (available_tools or [])
        if str(name).strip()
    }
    called_counter: Counter[str] = Counter()
    failed_counter: Counter[str] = Counter()
    retry_suppressed_counter: Counter[str] = Counter()
    deterministic_unsuppressed_counter: Counter[Tuple[str, str, str]] = Counter()
    skill_not_ready_tools: Set[str] = set()
    runtime_adapter_unavailable_tools: Set[str] = set()
    bootstrap_sources: List[str] = []

    for event in events:
        metadata = _event_get(event, "metadata", {}) or {}
        event_type = str(_event_get(event, "event_type", "") or "").strip()
        tool_name = str(_event_get(event, "tool_name", "") or "").strip()
        output_text = _tool_output_text(event)

        bootstrap_source = str(metadata.get("bootstrap_source") or "").strip()
        if bootstrap_source:
            bootstrap_sources.append(bootstrap_source)

        if event_type == "tool_call" and tool_name:
            called_counter[tool_name] += 1

        if event_type != "tool_result" or not tool_name:
            continue

        tool_status = str(metadata.get("tool_status") or "").strip().lower()
        if metadata.get("skill_not_ready") is True or "skill_not_ready:" in output_text:
            skill_not_ready_tools.add(tool_name)

        runtime_error = str(metadata.get("runtime_error") or "").strip()
        if (
            runtime_error.startswith("tool_adapter_unavailable:")
            or "tool_adapter_unavailable:" in output_text
        ):
            runtime_adapter_unavailable_tools.add(tool_name)

        if tool_status != "failed":
            continue

        failed_counter[tool_name] += 1
        if metadata.get("retry_suppressed") is True:
            retry_suppressed_counter[tool_name] += 1
            continue

        runtime_error_class = str(metadata.get("runtime_error_class") or "").strip()
        if runtime_error_class in NON_TRANSIENT_RUNTIME_ERROR_CLASSES:
            deterministic_unsuppressed_counter[
                (tool_name, runtime_error_class, runtime_error or output_text)
            ] += 1

    all_tools = sorted(available_set | set(called_counter.keys()) | set(failed_counter.keys()))
    matrix: Dict[str, Dict[str, Any]] = {}
    for tool_name in all_tools:
        matrix[tool_name] = {
            "available": tool_name in available_set if available_set else None,
            "called": int(called_counter.get(tool_name, 0)),
            "failed": int(failed_counter.get(tool_name, 0)),
            "retry_suppressed": int(retry_suppressed_counter.get(tool_name, 0)),
        }

    repeated_deterministic_failures = [
        {
            "tool_name": tool_name,
            "runtime_error_class": error_class,
            "runtime_error": runtime_error,
            "count": count,
        }
        for (tool_name, error_class, runtime_error), count in deterministic_unsuppressed_counter.items()
        if count > 1
    ]

    return {
        "matrix": matrix,
        "called_tools": sorted(called_counter.keys()),
        "failed_tools": sorted(tool_name for tool_name, count in failed_counter.items() if count > 0),
        "repeated_deterministic_failures": repeated_deterministic_failures,
        "bootstrap_sources": bootstrap_sources,
        "skill_not_ready_tools": sorted(skill_not_ready_tools),
        "runtime_adapter_unavailable_tools": sorted(runtime_adapter_unavailable_tools),
    }


def assert_scan_mode_coverage(
    *,
    mode: str,
    coverage: Dict[str, Any],
    embedded_bootstrap_expected: bool,
) -> None:
    normalized_mode = str(mode or "").strip().lower()
    failed_tools = list(coverage.get("failed_tools") or [])
    repeated_deterministic_failures = list(
        coverage.get("repeated_deterministic_failures") or []
    )
    bootstrap_sources = list(coverage.get("bootstrap_sources") or [])
    skill_not_ready_tools = list(coverage.get("skill_not_ready_tools") or [])
    runtime_adapter_unavailable_tools = list(
        coverage.get("runtime_adapter_unavailable_tools") or []
    )

    if normalized_mode == "intelligent":
        assert not failed_tools, (
            f"intelligent mode should not have failed tool_result, got: {failed_tools}"
        )

    if normalized_mode == "hybrid":
        assert not repeated_deterministic_failures, (
            "hybrid mode has repeated deterministic failures without suppression: "
            f"{repeated_deterministic_failures}"
        )
        if embedded_bootstrap_expected:
            assert "disabled_empty_seed" not in bootstrap_sources, (
                "hybrid mode with embedded bootstrap enabled should not emit "
                "bootstrap_source=disabled_empty_seed"
            )

    assert not skill_not_ready_tools, (
        f"enabled routes should not report skill_not_ready: {skill_not_ready_tools}"
    )
    assert not runtime_adapter_unavailable_tools, (
        "enabled routes should not report tool_adapter_unavailable: "
        f"{runtime_adapter_unavailable_tools}"
    )


def test_build_scan_mode_coverage_matrix_for_intelligent_mode():
    events = [
        {"event_type": "tool_call", "tool_name": "search_code"},
        {
            "event_type": "tool_result",
            "tool_name": "search_code",
            "tool_output": {"result": "ok"},
            "metadata": {"tool_status": "completed"},
        },
        {"event_type": "tool_call", "tool_name": "read_file"},
        {
            "event_type": "tool_result",
            "tool_name": "read_file",
            "tool_output": {"result": "ok"},
            "metadata": {"tool_status": "completed"},
        },
    ]

    coverage = build_scan_mode_coverage_matrix(
        events,
        available_tools=["search_code", "read_file", "pattern_match"],
    )
    assert coverage["failed_tools"] == []
    assert coverage["matrix"]["search_code"]["called"] == 1
    assert coverage["matrix"]["read_file"]["failed"] == 0

    assert_scan_mode_coverage(
        mode="intelligent",
        coverage=coverage,
        embedded_bootstrap_expected=False,
    )


def test_build_scan_mode_coverage_matrix_for_hybrid_mode_with_retry_suppression():
    events = [
        {
            "event_type": "info",
            "metadata": {
                "bootstrap": True,
                "bootstrap_source": "embedded_opengrep",
            },
        },
        {"event_type": "tool_call", "tool_name": "get_recon_risk_queue_status"},
        {
            "event_type": "tool_result",
            "tool_name": "get_recon_risk_queue_status",
            "tool_output": {"result": "strict failure"},
            "metadata": {
                "tool_status": "failed",
                "runtime_error": "'dict' object is not callable",
                "runtime_error_class": "invalid_callable_binding",
                "retry_suppressed": True,
            },
        },
    ]

    coverage = build_scan_mode_coverage_matrix(events)
    assert coverage["matrix"]["get_recon_risk_queue_status"]["failed"] == 1
    assert coverage["matrix"]["get_recon_risk_queue_status"]["retry_suppressed"] == 1
    assert coverage["repeated_deterministic_failures"] == []

    assert_scan_mode_coverage(
        mode="hybrid",
        coverage=coverage,
        embedded_bootstrap_expected=True,
    )


def test_assert_scan_mode_coverage_detects_hybrid_regressions():
    events = [
        {
            "event_type": "info",
            "metadata": {
                "bootstrap": True,
                "bootstrap_source": "disabled_empty_seed",
            },
        },
        {"event_type": "tool_call", "tool_name": "get_recon_risk_queue_status"},
        {
            "event_type": "tool_result",
            "tool_name": "get_recon_risk_queue_status",
            "tool_output": {"result": "failed#1"},
            "metadata": {
                "tool_status": "failed",
                "runtime_error": "'dict' object is not callable",
                "runtime_error_class": "invalid_callable_binding",
                "retry_suppressed": False,
            },
        },
        {"event_type": "tool_call", "tool_name": "get_recon_risk_queue_status"},
        {
            "event_type": "tool_result",
            "tool_name": "get_recon_risk_queue_status",
            "tool_output": {"result": "failed#2"},
            "metadata": {
                "tool_status": "failed",
                "runtime_error": "'dict' object is not callable",
                "runtime_error_class": "invalid_callable_binding",
                "retry_suppressed": False,
            },
        },
    ]

    coverage = build_scan_mode_coverage_matrix(events)
    assert len(coverage["repeated_deterministic_failures"]) == 1

    try:
        assert_scan_mode_coverage(
            mode="hybrid",
            coverage=coverage,
            embedded_bootstrap_expected=True,
        )
    except AssertionError:
        return
    raise AssertionError("expected hybrid regression assertions to fail")


def test_build_libplist_scan_request_uses_fixed_project_target():
    intelligent_payload = build_libplist_scan_request("intelligent")
    hybrid_payload = build_libplist_scan_request("hybrid")

    assert intelligent_payload["project_id"] == LIBPLIST_PROJECT_ID
    assert hybrid_payload["project_id"] == LIBPLIST_PROJECT_ID
    assert "[INTELLIGENT]" in intelligent_payload["name"]
    assert "[HYBRID]" in hybrid_payload["name"]
