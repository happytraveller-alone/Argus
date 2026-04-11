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
            "source": "request.args.get('name')",
            "sink": "asctime64_r(result)",
            "attacker_flow": "HTTP GET /time?name=... -> parse_name -> asctime64_r(result)",
            "taint_flow": [
                "request.args.get('name')",
                "parse_name(name)",
                "asctime64_r(result)",
            ],
            "finding_metadata": {
                "sink_reachable": True,
                "upstream_call_chain": [
                    "GET /time",
                    "parse_name(name)",
                    "asctime64_r(result)",
                ],
                "sink_trigger_condition": "攻击者可控 name 且调用链无长度约束",
            },
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


def test_verification_repair_final_answer_marks_false_positive_for_business_logic_when_source_sink_invalid():
    agent = _make_verification_agent()
    findings_to_verify = [
        {
            "title": "可疑漏洞",
            "vulnerability_type": "business_logic",
            "severity": "high",
            "file_path": "app/api/user.py",
            "line_start": 42,
            "line_end": 47,
            "description": "用户输入进入 SQL 执行",
            "source": "<source>",
            "sink": "cursor.execute(query)",
        }
    ]
    raw_answer = {
        "findings": [
            {
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "run_code 触发成功",
            }
        ]
    }

    repaired = agent._repair_final_answer(raw_answer, findings_to_verify, "analysis_with_poc_plan")
    finding = repaired["findings"][0]
    assert finding["verdict"] == "false_positive"
    assert finding["authenticity"] == "false_positive"
    assert finding["reachability"] == "unreachable"
    assert finding["is_verified"] is False
    assert finding["verification_result"]["source_sink_authenticity_passed"] is False
    assert "source/sink 真实性校验失败" in finding["verification_result"]["verification_evidence"]


def test_verification_repair_final_answer_keeps_non_target_verdict_with_placeholder_source_sink():
    agent = _make_verification_agent()
    findings_to_verify = [
        {
            "title": "可疑 SQL 注入",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "file_path": "app/api/user.py",
            "function_name": "query_user",
            "line_start": 42,
            "line_end": 47,
            "description": "用户输入进入 SQL 执行",
            "source": "<source>",
            "sink": "cursor.execute(query)",
        }
    ]
    raw_answer = {
        "findings": [
            {
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "run_code 触发成功",
            }
        ]
    }

    repaired = agent._repair_final_answer(raw_answer, findings_to_verify, "analysis_with_poc_plan")
    finding = repaired["findings"][0]
    assert finding["verdict"] == "confirmed"
    assert finding["is_verified"] is True
    assert finding["verification_result"].get("source_sink_authenticity_passed") is not False
    assert finding["verification_result"].get("source_sink_authenticity_errors") in (None, [])


def test_verification_repair_final_answer_keeps_non_dataflow_verdict_without_source_sink_fields():
    agent = _make_verification_agent()
    findings_to_verify = [
        {
            "title": "可疑 SQL 注入",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "file_path": "app/api/user.py",
            "function_name": "query_user",
            "line_start": 42,
            "line_end": 47,
            "description": "用户输入进入 SQL 执行",
        }
    ]
    raw_answer = {
        "findings": [
            {
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "run_code 触发成功",
            }
        ]
    }

    repaired = agent._repair_final_answer(raw_answer, findings_to_verify, "analysis_with_poc_plan")
    finding = repaired["findings"][0]
    assert finding["verdict"] == "confirmed"
    assert finding["is_verified"] is True
    assert finding["verification_result"].get("source_sink_authenticity_passed") is not False
    assert finding["verification_result"].get("source_sink_authenticity_errors") in (None, [])


def test_source_sink_gate_not_enforced_for_non_target_type_with_evidence_chain_only():
    agent = _make_verification_agent()
    finding = {
        "vulnerability_type": "command_injection",
        "source": "",
        "sink": "",
        "evidence_chain": ["get_code_window"],
        "status": "verified",
        "verdict": "confirmed",
        "verification_result": {
            "status": "verified",
            "verdict": "confirmed",
            "verification_evidence": "run_code 触发成功",
        },
    }

    normalized = agent._apply_source_sink_authenticity_gate(finding)
    assert normalized["verdict"] == "confirmed"
    assert normalized["status"] == "verified"
    assert normalized.get("is_verified") is not False
    assert normalized["verification_result"].get("source_sink_authenticity_passed") is not False
    assert normalized["verification_result"].get("source_sink_authenticity_errors") in (None, [])


def test_source_sink_gate_prefers_valid_fallback_over_placeholder_values():
    agent = _make_verification_agent()
    finding = {
        "vulnerability_type": "business_logic",
        "source": "<source>",
        "sink": "<sink>",
        "verification_result": {},
    }
    fallback = {
        "vulnerability_type": "business_logic",
        "source": "request.args.get('order_id')",
        "sink": "Order.query.get(order_id)",
        "attacker_flow": "PUT /orders/{id} -> update_order -> Order.query.get(order_id)",
        "evidence_chain": ["get_code_window", "dataflow_analysis"],
        "finding_metadata": {
            "sink_reachable": True,
            "upstream_call_chain": ["PUT /orders/{id}", "update_order(order_id)"],
            "sink_trigger_condition": "攻击者可控 order_id 且无 owner 校验",
        },
    }

    normalized = agent._apply_source_sink_authenticity_gate(finding, fallback=fallback)
    assert normalized["source"] == fallback["source"]
    assert normalized["sink"] == fallback["sink"]
    assert normalized["verification_result"]["source_sink_authenticity_passed"] is True
    assert normalized["verification_result"].get("source_sink_authenticity_errors") in (None, [])


def test_source_sink_gate_preserves_existing_finding_metadata():
    agent = _make_verification_agent()
    finding = {
        "vulnerability_type": "business_logic",
        "source": "request.args.get('order_id')",
        "sink": "Order.query.get(order_id)",
        "attacker_flow": "PUT /orders/{id} -> update_order -> Order.query.get(order_id)",
        "evidence_chain": ["get_code_window"],
        "finding_metadata": {
            "sink_reachable": True,
            "upstream_call_chain": ["PUT /orders/{id}", "update_order(order_id)"],
            "sink_trigger_condition": "攻击者可控 order_id 且无 owner 校验",
            "verification_todo_id": "todo-001",
            "custom_tag": "keep-me",
        },
        "verification_result": {},
    }

    normalized = agent._apply_source_sink_authenticity_gate(finding)
    metadata = normalized.get("finding_metadata") or {}
    assert metadata.get("verification_todo_id") == "todo-001"
    assert metadata.get("custom_tag") == "keep-me"
    assert metadata.get("sink_reachable") is True
    assert normalized["verification_result"]["source_sink_authenticity_passed"] is True


def test_select_fallback_finding_prefers_identity_over_index_alignment():
    agent = _make_verification_agent()
    fallback_findings = [
        {
            "finding_identity": "finding-a",
            "vulnerability_type": "idor",
            "file_path": "app/a.py",
            "line_start": 10,
            "title": "A",
        },
        {
            "finding_identity": "finding-b",
            "vulnerability_type": "idor",
            "file_path": "app/b.py",
            "line_start": 20,
            "title": "B",
        },
    ]
    used_indexes = set()

    matched = agent._select_fallback_finding(
        {
            "finding_identity": "finding-b",
            "vulnerability_type": "idor",
            "file_path": "app/b.py",
            "line_start": 20,
            "title": "B",
        },
        fallback_findings,
        used_indexes,
        preferred_index=0,
    )
    assert isinstance(matched, dict)
    assert matched["finding_identity"] == "finding-b"

    matched_second = agent._select_fallback_finding(
        {
            "finding_identity": "finding-a",
            "vulnerability_type": "idor",
            "file_path": "app/a.py",
            "line_start": 10,
            "title": "A",
        },
        fallback_findings,
        used_indexes,
        preferred_index=1,
    )
    assert isinstance(matched_second, dict)
    assert matched_second["finding_identity"] == "finding-a"


def test_select_fallback_finding_uses_best_candidate_when_preferred_index_unavailable():
    agent = _make_verification_agent()
    fallback_findings = [
        {
            "finding_identity": "finding-a",
            "vulnerability_type": "idor",
            "file_path": "app/a.py",
            "line_start": 10,
            "title": "A",
        },
        {
            "finding_identity": "finding-b",
            "vulnerability_type": "idor",
            "file_path": "app/b.py",
            "line_start": 20,
            "title": "B",
        },
    ]
    used_indexes = {1}

    matched = agent._select_fallback_finding(
        {"verdict": "confirmed"},
        fallback_findings,
        used_indexes,
        preferred_index=1,
    )
    assert isinstance(matched, dict)
    assert matched["finding_identity"] == "finding-a"


def test_select_fallback_finding_does_not_bias_to_line_one_when_line_missing():
    agent = _make_verification_agent()
    fallback_findings = [
        {
            "finding_identity": "finding-line-1",
            "vulnerability_type": "idor",
            "file_path": "app/orders.py",
            "line_start": 1,
            "title": "订单越权",
        },
        {
            "finding_identity": "finding-line-200",
            "vulnerability_type": "idor",
            "file_path": "app/orders.py",
            "line_start": 200,
            "title": "订单越权",
        },
    ]
    used_indexes = set()

    matched = agent._select_fallback_finding(
        {
            "vulnerability_type": "idor",
            "file_path": "app/orders.py",
            "title": "订单越权",
        },
        fallback_findings,
        used_indexes,
        preferred_index=1,
    )
    assert isinstance(matched, dict)
    assert matched["finding_identity"] == "finding-line-200"


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
