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
    assert finding["reachability"] in {"reachable", "likely_reachable", "unreachable"}
    assert finding["suggestion"]
    assert finding["fix_code"]
    assert finding.get("poc") is not None


def test_verification_repair_final_answer_adds_poc_plan_for_confirmed_or_likely():
    agent = _make_agent()
    findings_to_verify = [
        {
            "title": "critical cmd injection",
            "vulnerability_type": "command_injection",
            "severity": "critical",
            "file_path": "src/cmd.py",
            "line_start": 10,
            "line_end": 10,
        },
        {
            "title": "medium xss",
            "vulnerability_type": "xss",
            "severity": "medium",
            "file_path": "src/view.py",
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
async def test_verification_skips_when_no_opengrep_error_candidates_even_if_analysis_findings_exist(monkeypatch):
    agent = _make_agent_for_run()

    # Should not call LLM when no candidates.
    monkeypatch.setattr(
        agent,
        "stream_llm_call",
        AsyncMock(side_effect=AssertionError("stream_llm_call should not be called")),
    )

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
    assert result.iterations == 0
    assert result.data["verified_count"] == 0
    assert result.data["findings"] == []


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
async def test_verification_scope_uses_only_bootstrap_candidates_and_caps_at_8(monkeypatch):
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
    assert len(findings) == 8  # cap enforced
    assert all(f.get("file_path", "").startswith("src/candidate_") for f in findings)
    assert all(f.get("file_path") != "src/from_analysis.py" for f in findings)
