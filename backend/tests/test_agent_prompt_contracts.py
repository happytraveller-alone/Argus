import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401

from app.services.agent.agents.analysis import ANALYSIS_SYSTEM_PROMPT
from app.services.agent.agents.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
from app.services.agent.agents.recon import RECON_SYSTEM_PROMPT
from app.services.agent.agents.verification import VERIFICATION_SYSTEM_PROMPT
from app.services.agent.prompts.system_prompts import TOOL_USAGE_GUIDE


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


def test_verification_prompt_requires_flow_fields_and_report_preconditions():
    assert "verification_result.flow" in VERIFICATION_SYSTEM_PROMPT
    assert "function_trigger_flow" in VERIFICATION_SYSTEM_PROMPT
    assert "create_vulnerability_report" in VERIFICATION_SYSTEM_PROMPT
    assert "标题结构化" in VERIFICATION_SYSTEM_PROMPT
    assert "src/time64.c中asctime64_r栈溢出漏洞" in VERIFICATION_SYSTEM_PROMPT


def test_shared_tool_usage_prompt_includes_flow_tools_and_code_search_alias():
    assert "dataflow_analysis" in TOOL_USAGE_GUIDE
    assert "controlflow_analysis_light" in TOOL_USAGE_GUIDE
    assert "logic_authz_analysis" in TOOL_USAGE_GUIDE
    assert "code_search" in TOOL_USAGE_GUIDE
