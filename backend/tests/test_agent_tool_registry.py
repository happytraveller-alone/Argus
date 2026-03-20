from unittest.mock import MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _initialize_tools


REMOVED_TOOL_NAMES = {
    "skill_lookup",
    "qmd_query",
    "qmd_get",
    "qmd_multi_get",
    "qmd_status",
    "sequential_thinking",
    "reasoning_trace",
    "query_security_knowledge",
    "get_vulnerability_knowledge",
    "php_test",
    "python_test",
    "javascript_test",
    "java_test",
    "go_test",
    "ruby_test",
    "shell_test",
    "universal_code_test",
    "test_command_injection",
    "test_sql_injection",
    "test_xss",
    "test_path_traversal",
    "test_ssti",
    "test_deserialization",
    "universal_vuln_test",
    "sandbox_http",
}

PUBLIC_CORE_SKILLS = {
    "search_code",
    "list_files",
    "get_code_window",
    "get_file_outline",
    "get_function_summary",
    "get_symbol_body",
    "smart_scan",
    "quick_audit",
    "pattern_match",
    "dataflow_analysis",
    "controlflow_analysis_light",
    "logic_authz_analysis",
    "run_code",
    "sandbox_exec",
    "verify_vulnerability",
    "create_vulnerability_report",
}


@pytest.mark.asyncio
async def test_smart_audit_tool_registry_contains_only_core_scan_surface(tmp_path):
    tools = await _initialize_tools(
        project_root=str(tmp_path),
        llm_service=MagicMock(),
        user_config=None,
        sandbox_manager=MagicMock(),
        exclude_patterns=[],
        target_files=[],
        event_emitter=None,
        task_id=None,
    )

    analysis_names = set(tools["analysis"].keys())
    verification_names = set(tools["verification"].keys())
    orchestrator_names = set(tools["orchestrator"].keys())
    recon_names = set(tools["recon"].keys())

    assert {"search_code", "list_files", "get_file_outline", "get_code_window"}.issubset(recon_names)
    assert {
        "search_code",
        "list_files",
        "get_code_window",
        "get_function_summary",
        "get_symbol_body",
        "smart_scan",
        "quick_audit",
        "pattern_match",
        "dataflow_analysis",
        "controlflow_analysis_light",
        "logic_authz_analysis",
    }.issubset(analysis_names)
    assert {
        "search_code",
        "list_files",
        "get_code_window",
        "get_function_summary",
        "get_symbol_body",
        "run_code",
        "sandbox_exec",
        "verify_vulnerability",
        "create_vulnerability_report",
    }.issubset(verification_names)
    assert {"search_code", "list_files", "get_code_window", "get_file_outline"}.issubset(
        orchestrator_names
    )

    for tool_set in (analysis_names, verification_names, orchestrator_names, recon_names):
        assert not (REMOVED_TOOL_NAMES & tool_set)
        assert "read_file" not in tool_set
        assert "extract_function" not in tool_set

    assert PUBLIC_CORE_SKILLS - {"sandbox_exec", "verify_vulnerability", "run_code", "create_vulnerability_report", "smart_scan", "quick_audit", "pattern_match", "dataflow_analysis", "controlflow_analysis_light", "logic_authz_analysis"}
