import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401

from app.services.agent.agents.analysis import ANALYSIS_SYSTEM_PROMPT
from app.services.agent.agents.business_logic_analysis import BL_ANALYSIS_SYSTEM_PROMPT
from app.services.agent.agents.business_logic_recon import BL_RECON_SYSTEM_PROMPT
from app.services.agent.agents.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
from app.services.agent.agents.recon import RECON_SYSTEM_PROMPT
from app.services.agent.agents.verification import VERIFICATION_SYSTEM_PROMPT
from app.services.agent.prompts.system_prompts import TOOL_USAGE_GUIDE


REMOVED_PROMPT_TOKENS = [
    "qmd_query",
    "qmd_get",
    "sequential_thinking",
    "reasoning_trace",
    "skill_lookup",
    "sandbox_http",
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
]


def test_orchestrator_prompt_requires_flow_evidence_gate():
    assert "高危候选" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "flow 证据" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "dataflow_analysis" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "controlflow_analysis_light" in ORCHESTRATOR_SYSTEM_PROMPT



def test_recon_prompt_requires_input_surfaces_and_trust_boundaries():
    assert "input_surfaces" in RECON_SYSTEM_PROMPT
    assert "trust_boundaries" in RECON_SYSTEM_PROMPT
    assert "target_files" in RECON_SYSTEM_PROMPT
    assert "高风险区域" in RECON_SYSTEM_PROMPT



def test_analysis_prompt_requires_two_evidence_classes_and_structured_title():
    assert "2 类证据" in ANALYSIS_SYSTEM_PROMPT
    assert "代码证据" in ANALYSIS_SYSTEM_PROMPT
    assert "流证据" in ANALYSIS_SYSTEM_PROMPT
    assert "dataflow_analysis/controlflow_analysis_light" in ANALYSIS_SYSTEM_PROMPT
    assert "src/time64.c中asctime64_r栈溢出漏洞" in ANALYSIS_SYSTEM_PROMPT
    assert '"file_path": "src/example.py"' in ANALYSIS_SYSTEM_PROMPT
    assert "Action Input: {\n    \"finding\": {" not in ANALYSIS_SYSTEM_PROMPT
    assert "file_path:line" in ANALYSIS_SYSTEM_PROMPT
    assert "line_start" in ANALYSIS_SYSTEM_PROMPT



def test_business_logic_prompts_require_tool_usage_and_failure_handling():
    assert "工具使用方法（必须遵循）" in BL_RECON_SYSTEM_PROMPT
    assert "工具调用失败处理（关键）" in BL_RECON_SYSTEM_PROMPT
    assert "Action Input" in BL_RECON_SYSTEM_PROMPT
    assert "list_files" in BL_RECON_SYSTEM_PROMPT
    assert "push_bl_risk_point_to_queue" in BL_RECON_SYSTEM_PROMPT

    assert "工具使用方法（必须遵循）" in BL_ANALYSIS_SYSTEM_PROMPT
    assert "工具调用失败处理（关键）" in BL_ANALYSIS_SYSTEM_PROMPT
    assert "Action Input" in BL_ANALYSIS_SYSTEM_PROMPT
    assert "get_code_window" in BL_ANALYSIS_SYSTEM_PROMPT
    assert "get_function_summary" in BL_ANALYSIS_SYSTEM_PROMPT
    assert "push_finding_to_queue" in BL_ANALYSIS_SYSTEM_PROMPT



def test_verification_prompt_requires_flow_fields_and_report_preconditions():
    assert "verification_result.flow" in VERIFICATION_SYSTEM_PROMPT
    assert "function_trigger_flow" in VERIFICATION_SYSTEM_PROMPT
    assert "save_verification_result" in VERIFICATION_SYSTEM_PROMPT
    assert "标题结构化" in VERIFICATION_SYSTEM_PROMPT
    assert "src/time64.c中asctime64_r栈溢出漏洞" in VERIFICATION_SYSTEM_PROMPT
    assert "run_code" in VERIFICATION_SYSTEM_PROMPT
    assert "sandbox_exec" in VERIFICATION_SYSTEM_PROMPT



def test_shared_tool_usage_prompt_only_mentions_core_scan_tools():
    assert "dataflow_analysis" in TOOL_USAGE_GUIDE
    assert "controlflow_analysis_light" in TOOL_USAGE_GUIDE
    assert "logic_authz_analysis" in TOOL_USAGE_GUIDE
    assert "smart_scan" in TOOL_USAGE_GUIDE
    assert "quick_audit" in TOOL_USAGE_GUIDE
    assert "run_code" in TOOL_USAGE_GUIDE
    assert "verify_vulnerability" in TOOL_USAGE_GUIDE
    assert "先用 `search_code` 定位到 `file_path:line`" in TOOL_USAGE_GUIDE
    assert "get_code_window" in TOOL_USAGE_GUIDE
    assert "get_function_summary" in TOOL_USAGE_GUIDE
    assert "get_symbol_body" in TOOL_USAGE_GUIDE
    assert "code_search" not in TOOL_USAGE_GUIDE
    assert "read_file" not in TOOL_USAGE_GUIDE
    assert "extract_function" not in TOOL_USAGE_GUIDE
    for token in REMOVED_PROMPT_TOKENS:
        assert token not in TOOL_USAGE_GUIDE
