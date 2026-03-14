from types import SimpleNamespace

import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401

from app.api.v1.endpoints.agent_tasks import (
    _build_structured_cn_description,
    _build_structured_cn_display_title,
)
from app.services.agent.agents.orchestrator import OrchestratorAgent
from app.services.agent.agents.verification import VerificationAgent
from app.services.agent.utils.vulnerability_naming import (
    build_cn_structured_title,
    resolve_vulnerability_profile,
)


def _make_orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent(
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=None,
        sub_agents={},
    )


def _make_verification_agent() -> VerificationAgent:
    return VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": object()},
        event_emitter=None,
    )


def test_vulnerability_profile_refines_other_type_for_memory_signal():
    profile = resolve_vulnerability_profile(
        "other",
        title="asctime64_r potential issue",
        description="发现 sprintf 写入固定缓冲区",
        code_snippet='sprintf(result, "%s", input);',
    )
    assert profile["key"] == "stack_overflow"
    assert profile["name"] == "栈溢出漏洞"


def test_build_cn_structured_title_is_three_segment_and_without_harm_suffix():
    title = build_cn_structured_title(
        file_path="src/time64.c",
        function_name="asctime64_r",
        vulnerability_type="other",
        title="安全漏洞",
        description="sprintf 未做长度约束",
        code_snippet='sprintf(result, "%s", input);',
    )
    assert title == "src/time64.c中asctime64_r栈溢出漏洞"
    assert "可能造成的危害" not in title
    assert "安全漏洞" not in title


def test_orchestrator_normalize_finding_outputs_structured_title():
    orchestrator = _make_orchestrator()
    finding = {
        "title": "安全漏洞",
        "vulnerability_type": "other",
        "severity": "high",
        "file_path": "src/time64.c",
        "function_name": "asctime64_r",
        "line_start": 168,
        "description": "sprintf 未校验长度",
        "code_snippet": 'sprintf(result, "%s", input);',
    }

    normalized = orchestrator._normalize_finding(finding)
    assert isinstance(normalized, dict)
    assert normalized["title"] == "src/time64.c中asctime64_r栈溢出漏洞"
    assert normalized["display_title"] == normalized["title"]
    assert normalized["vulnerability_type"] == "stack_overflow"
    assert "可能造成的危害" not in normalized["title"]


def test_verification_repair_final_answer_uses_structured_title():
    agent = _make_verification_agent()
    findings_to_verify = [
        {
            "title": "安全漏洞",
            "vulnerability_type": "other",
            "severity": "high",
            "file_path": "src/time64.c",
            "function_name": "asctime64_r",
            "line_start": 168,
            "line_end": 172,
            "code_snippet": 'sprintf(result, "%s", input);',
            "description": "边界检查缺失",
        }
    ]
    raw_answer = {
        "findings": [
            {
                "title": "待确认",
                "vulnerability_type": "other",
                "severity": "high",
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "read_file + flow 复核通过",
            }
        ]
    }

    repaired = agent._repair_final_answer(raw_answer, findings_to_verify, "analysis_with_poc_plan")
    finding = repaired["findings"][0]
    assert finding["title"] == "src/time64.c中asctime64_r栈溢出漏洞"
    assert finding["display_title"] == finding["title"]
    assert finding["vulnerability_type"] == "stack_overflow"
    assert "可能造成的危害" not in finding["title"]


def test_agent_tasks_structured_helpers_follow_three_segment_contract():
    display_title = _build_structured_cn_display_title(
        file_path="src/time64.c",
        function_name="asctime64_r",
        vulnerability_type="other",
        title="安全漏洞",
        description="sprintf 写入风险",
        code_snippet='sprintf(result, "%s", input);',
    )
    description = _build_structured_cn_description(
        file_path="src/time64.c",
        function_name="asctime64_r",
        vulnerability_type="other",
        title="安全漏洞",
        description="sprintf 写入风险",
        code_snippet='sprintf(result, "%s", input);',
        cwe_id="CWE-121",
        raw_description="复核命中栈写入边界问题",
    )

    assert display_title == "src/time64.c中asctime64_r栈溢出漏洞"
    assert "该漏洞位于src/time64.c的asctime64_r函数中" in description
    assert "代码存在栈溢出漏洞" in description
    assert "命中代码片段为" in description or "证据不足" in description
    assert "程序在该路径上缺少必要的输入约束或边界校验处理" in description
    assert "可能造成的危害" not in description
    assert "漏洞详情：" not in description
    assert "代码证据（实际片段）" not in description
    assert "```" not in description
    assert "\n- " not in description
