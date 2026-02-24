from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.verification import VerificationAgent
from app.services.agent.tools.base import ToolResult
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


def _make_agent() -> VerificationAgent:
    return VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": object(), "extract_function": object()},
        event_emitter=None,
    )


class _DummyTool:
    def __init__(self, data: str):
        self.description = "dummy tool"
        self._data = data

    async def execute(self, **kwargs):
        return ToolResult(success=True, data=self._data)


def _make_agent_for_run() -> VerificationAgent:
    return VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={
            "read_file": _DummyTool("dummy file content"),
            "search_code": _DummyTool("dummy search result"),
        },
        event_emitter=None,
    )


def test_verification_detects_interactive_drift_patterns():
    agent = _make_agent()
    assert agent._contains_interactive_drift("你需要选择下一步操作")
    assert agent._contains_interactive_drift("Please confirm whether to continue")
    assert not agent._contains_interactive_drift("已完成验证并输出结果")


def test_verification_repair_final_answer_fills_required_fields_and_defaults():
    agent = _make_agent()
    findings_to_verify = [
        {
            "title": "SQL injection in query endpoint",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "file_path": "src/api/query.py",
            "function_name": "query_endpoint",
            "line_start": 88,
            "line_end": 89,
            "code_snippet": "cursor.execute(f\"SELECT * FROM t WHERE id = '{user_id}'\")",
        }
    ]
    raw_answer = {
        "findings": [
            {
                "title": "SQL injection in query endpoint",
                "severity": "high",
                "vulnerability_type": "sql_injection",
                "verdict": "confirmed",
            }
        ]
    }

    repaired = agent._repair_final_answer(
        raw_answer,
        findings_to_verify,
        "analysis_with_poc_plan",
    )
    ok, err = agent._validate_final_answer_schema(repaired)

    assert ok, err
    finding = repaired["findings"][0]
    assert finding["file_path"] == "src/api/query.py"
    assert finding["line_start"] == 88
    assert finding["line_end"] == 89
    assert finding["title"] == "src/api/query.py中query_endpointSQL注入漏洞"
    assert finding["display_title"] == finding["title"]
    assert finding["vulnerability_type"] == "sql_injection"
    assert "可能造成的危害" not in finding["title"]
    assert finding["reachability"] in {"reachable", "likely_reachable", "unreachable"}
    assert finding["suggestion"]
    assert finding["fix_code"]
    assert finding.get("poc") is not None
    assert isinstance(finding.get("verification_result"), dict)
    assert finding["verification_result"].get("authenticity") in {"confirmed", "likely", "false_positive"}
    assert finding["verification_result"].get("reachability") in {"reachable", "likely_reachable", "unreachable"}
    assert isinstance(finding["verification_result"].get("function_trigger_flow"), list)
    reachability_target = finding["verification_result"].get("reachability_target")
    assert isinstance(reachability_target, dict)
    assert reachability_target.get("file_path")
    assert reachability_target.get("function")


def test_verification_repair_final_answer_keeps_full_candidate_coverage_when_llm_partial():
    agent = _make_agent()
    findings_to_verify = [
        {
            "title": "candidate-1",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "file_path": "src/a.py",
            "function_name": "build_query",
            "line_start": 10,
            "line_end": 10,
            "code_snippet": "query = user_input",
        },
        {
            "title": "candidate-2",
            "vulnerability_type": "xss",
            "severity": "medium",
            "file_path": "src/b.py",
            "function_name": "render_html",
            "line_start": 20,
            "line_end": 20,
            "code_snippet": "innerHTML = value",
        },
    ]
    raw_answer = {
        "findings": [
            {
                "title": "candidate-1",
                "vulnerability_type": "sql_injection",
                "severity": "high",
                "file_path": "src/a.py",
                "line_start": 10,
                "line_end": 10,
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "ok",
            }
        ]
    }

    repaired = agent._repair_final_answer(
        raw_answer,
        findings_to_verify,
        "analysis_with_poc_plan",
    )
    findings = repaired.get("findings")
    assert isinstance(findings, list)
    assert len(findings) == 2
    assert all(isinstance(item.get("verification_result"), dict) for item in findings)


def test_verification_repair_final_answer_adds_poc_plan_for_confirmed_or_likely():
    agent = _make_agent()
    findings_to_verify = [
        {
            "title": "critical cmd injection",
            "vulnerability_type": "command_injection",
            "severity": "critical",
            "file_path": "src/cmd.py",
            "function_name": "run_cmd",
            "line_start": 10,
            "line_end": 10,
        },
        {
            "title": "medium xss",
            "vulnerability_type": "xss",
            "severity": "medium",
            "file_path": "src/view.py",
            "function_name": "render_view",
            "line_start": 20,
            "line_end": 20,
        },
    ]
    raw_answer = {
        "findings": [
            {
                "title": "critical cmd injection",
                "severity": "critical",
                "vulnerability_type": "command_injection",
                "file_path": "src/cmd.py",
                "line_start": 10,
                "line_end": 10,
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "confirmed by harness",
                "poc": {"description": "poc", "payload": "python poc.py"},
            },
            {
                "title": "medium xss",
                "severity": "medium",
                "vulnerability_type": "xss",
                "file_path": "src/view.py",
                "line_start": 20,
                "line_end": 20,
                "verdict": "confirmed",
                "reachability": "reachable",
                "verification_details": "confirmed by read_file",
                "poc": {"description": "should be removed", "payload": "bad"},
            },
        ]
    }

    repaired = agent._repair_final_answer(
        raw_answer,
        findings_to_verify,
        "analysis_with_poc_plan",
    )

    assert repaired["findings"][0].get("poc") is not None
    assert repaired["findings"][1].get("poc") is not None


@pytest.mark.asyncio
async def test_verification_uses_analysis_findings_when_bootstrap_empty(monkeypatch):
    agent = _make_agent_for_run()

    llm_side_effects = [
        ("Thought: done\nFinal Answer: {}", 10),
        ("Thought: done\nFinal Answer: {}", 10),
    ]
    monkeypatch.setattr(agent, "stream_llm_call", AsyncMock(side_effect=llm_side_effects))

    result = await agent.run(
        {
            "config": {},
            "previous_results": {
                "analysis": {
                    "data": {
                        "findings": [
                            {
                                "severity": "high",
                                "confidence": 0.9,
                                "file_path": "src/from_analysis.py",
                                "line_start": 1,
                                "vulnerability_type": "sql_injection",
                                "title": "analysis finding",
                            }
                        ]
                    }
                },
                # No bootstrap candidates => should skip.
                "bootstrap_findings": [],
            },
            "task": "verify",
        }
    )

    assert result.success is True
    assert result.tool_calls >= 1
    assert result.data["candidate_count"] == 1
    assert len(result.data["findings"]) == 1
    assert result.data["findings"][0]["file_path"] == "src/from_analysis.py"


@pytest.mark.asyncio
async def test_verification_forces_min_tool_call_when_llm_tries_to_finish_without_action(monkeypatch):
    agent = _make_agent_for_run()

    # LLM stubbornly outputs Final Answer twice (no Action).
    llm_side_effects = [
        ("Thought: done\nFinal Answer: {}", 10),
        ("Thought: done\nFinal Answer: {}", 10),
    ]
    monkeypatch.setattr(agent, "stream_llm_call", AsyncMock(side_effect=llm_side_effects))

    result = await agent.run(
        {
            "config": {},
            "previous_results": {
                "bootstrap_findings": [
                    {
                        "id": "candidate-1",
                        "severity": "ERROR",
                        "confidence": "HIGH",
                        "file_path": "src/a.py",
                        "line_start": 10,
                        "vulnerability_type": "sql_injection",
                        "title": "bootstrap candidate",
                        "description": "desc",
                        "code_snippet": "danger()",
                    }
                ]
            },
            "task": "verify",
        }
    )

    assert result.success is True
    assert result.tool_calls >= 1  # forced read_file should have happened
    assert result.iterations <= 2  # should converge quickly
    assert isinstance(result.data.get("findings"), list)
    assert result.data["findings"]


@pytest.mark.asyncio
async def test_verification_scope_merges_all_candidates_without_hard_cap(monkeypatch):
    agent = _make_agent_for_run()

    bootstrap_findings = []
    for i in range(10):
        bootstrap_findings.append(
            {
                "id": f"candidate-{i}",
                "severity": "ERROR",
                "confidence": "HIGH",
                "file_path": f"src/candidate_{i}.py",
                "line_start": i + 1,
                "vulnerability_type": "sql_injection",
                "title": f"bootstrap {i}",
                "description": "desc",
                "code_snippet": "danger()",
            }
        )
    # Noise that must be ignored.
    bootstrap_findings.append(
        {
            "id": "ignored-warning",
            "severity": "WARNING",
            "confidence": "HIGH",
            "file_path": "src/ignored.py",
            "line_start": 1,
            "vulnerability_type": "other",
            "title": "ignored",
        }
    )

    llm_side_effects = [
        ("Thought: done\nFinal Answer: {}", 10),
        ("Thought: done\nFinal Answer: {}", 10),
    ]
    monkeypatch.setattr(agent, "stream_llm_call", AsyncMock(side_effect=llm_side_effects))

    result = await agent.run(
        {
            "config": {},
            "previous_results": {
                "analysis": {
                    "data": {
                        "findings": [
                            {
                                "severity": "critical",
                                "confidence": 0.95,
                                "file_path": "src/from_analysis.py",
                                "line_start": 999,
                                "vulnerability_type": "command_injection",
                                "title": "analysis finding",
                            }
                        ]
                    }
                },
                "bootstrap_findings": bootstrap_findings,
            },
            "task": "verify",
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) == 12
    assert any(f.get("file_path") == "src/from_analysis.py" for f in findings)
    assert any(f.get("file_path") == "src/ignored.py" for f in findings)
    assert result.data.get("candidate_count") == 12


@pytest.mark.asyncio
async def test_verification_cancel_message_uses_current_run_iteration(monkeypatch):
    agent = _make_agent_for_run()
    agent._iteration = 14
    agent._cancelled = True

    emit_spy = AsyncMock()
    monkeypatch.setattr(agent, "emit_event", emit_spy)

    result = await agent.run(
        {
            "config": {},
            "previous_results": {
                "bootstrap_findings": [
                    {
                        "severity": "high",
                        "confidence": 0.9,
                        "file_path": "src/a.py",
                        "line_start": 10,
                        "vulnerability_type": "sql_injection",
                        "title": "bootstrap candidate",
                    }
                ]
            },
            "task": "verify",
        }
    )

    assert result.success is False
    assert result.error == "任务已取消"
    assert result.iterations == 0

    cancel_messages = [
        call.args[1]
        for call in emit_spy.await_args_list
        if len(call.args) >= 2
        and call.args[0] == "info"
        and isinstance(call.args[1], str)
        and "Verification Agent 已取消" in call.args[1]
    ]
    assert cancel_messages
    assert "Verification Agent 已取消: 本次迭代 0" in cancel_messages[-1]
    assert "当前漏洞 0/1" in cancel_messages[-1]

    cancel_metadata = [
        call.kwargs.get("metadata")
        for call in emit_spy.await_args_list
        if len(call.args) >= 2
        and call.args[0] == "info"
        and isinstance(call.args[1], str)
        and "Verification Agent 已取消" in call.args[1]
    ]
    assert cancel_metadata
    latest_metadata = cancel_metadata[-1] or {}
    assert latest_metadata.get("run_iteration_count") == 0
    assert latest_metadata.get("total_todos") == 1
