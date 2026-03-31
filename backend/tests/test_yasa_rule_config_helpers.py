from fastapi import HTTPException

from app.api.v1.endpoints.static_tasks_yasa import (
    _assert_yasa_project_language_supported,
    _merge_task_diagnostics_summary,
    _normalize_checker_values,
    _parse_rule_config_checker_ids,
    _validate_checker_bindings,
)


def test_parse_rule_config_checker_ids_from_list_payload():
    payload = [
        {"checkerIds": ["taint_flow_go_input", "callgraph"]},
        {"checkerIds": ["callgraph", "sanitizer"]},
    ]

    assert _parse_rule_config_checker_ids(payload) == [
        "taint_flow_go_input",
        "callgraph",
        "sanitizer",
    ]


def test_normalize_checker_values_deduplicates_and_trims():
    assert _normalize_checker_values([" callgraph ", "", "callgraph", "sanitizer"]) == [
        "callgraph",
        "sanitizer",
    ]


def test_validate_checker_bindings_rejects_unknown_ids():
    catalog = {
        "checker_ids": {"callgraph", "sanitizer"},
        "checker_pack_ids": {"taint-flow-golang-default"},
    }

    try:
        _validate_checker_bindings(
            checker_ids=["unknown_checker"],
            checker_pack_ids=["taint-flow-golang-default"],
            catalog=catalog,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "未知 checkerIds" in str(exc.detail)
    else:
        raise AssertionError("Expected HTTPException")


def test_assert_yasa_project_language_supported_rejects_non_whitelist_language():
    class _Project:
        programming_languages = '["javascript"]'

    try:
        _assert_yasa_project_language_supported(_Project())
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "YASA 引擎仅支持 Java / Go / TypeScript / Python 项目" in str(exc.detail)
    else:
        raise AssertionError("Expected HTTPException")


def test_merge_task_diagnostics_summary_merges_dict_payload():
    existing = '{"termination_reason":"completed","rule_config":{"id":"1"}}'
    merged = _merge_task_diagnostics_summary(
        existing,
        {"termination_reason": "orphan_recovery", "orphan_recovered": True},
    )

    assert merged is not None
    assert "orphan_recovered" in merged
    assert "orphan_recovery" in merged


def test_merge_task_diagnostics_summary_wraps_plain_text():
    merged = _merge_task_diagnostics_summary(
        "plain summary text",
        {"termination_reason": "timeout"},
    )
    assert merged is not None
    assert "plain summary text" in merged
    assert "timeout" in merged
