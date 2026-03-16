from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.agent_tasks import _save_findings
from app.models.agent_task import AgentFinding
from app.services.agent.agents.report import ReportAgent
from app.services.agent.tools.base import AgentTool, ToolResult
from app.services.agent.tools.verification_result_tools import (
    SaveVerificationResultTool,
    UpdateVulnerabilityFindingTool,
)


class _SequenceLLM:
    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)

    async def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2):
        if not self._responses:
            raise RuntimeError("no more llm responses")
        return {"content": self._responses.pop(0), "usage": {"total_tokens": 7}}


class _ReadFileTool(AgentTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "read file"

    async def _execute(self, file_path: str, start_line: int = 1, end_line: int = 20) -> ToolResult:
        content = "\n".join(
            [
                "10 def correct_func(user_input):",
                "11     sink(user_input)",
            ]
        )
        return ToolResult(success=True, data={"file_path": file_path, "content": content})


@pytest.mark.asyncio
async def test_save_verification_result_generates_finding_identity():
    buffered: List[Dict[str, Any]] = []

    async def _save_callback(findings: List[Dict[str, Any]]) -> int:
        buffered.extend(findings)
        return len(findings)

    tool = SaveVerificationResultTool(task_id="task-1", save_callback=_save_callback)
    result = await tool.execute(
        file_path="app/a.py",
        line_start=11,
        function_name="demo",
        title="app/a.py中demo函数SQL注入漏洞",
        vulnerability_type="sql_injection",
        severity="high",
        verdict="confirmed",
        confidence=0.9,
        reachability="reachable",
        verification_evidence="dynamic verification evidence is sufficient",
    )

    assert result.success is True
    assert buffered
    assert buffered[0]["finding_identity"].startswith("fid:")
    assert buffered[0]["verification_result"]["finding_identity"] == buffered[0]["finding_identity"]


@pytest.mark.asyncio
async def test_update_vulnerability_finding_rejects_verdict_patch():
    async def _update_callback(identity: str, patch: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {"finding_identity": identity, **patch}

    tool = UpdateVulnerabilityFindingTool(task_id="task-2", update_callback=_update_callback)
    result = await tool.execute(
        finding_identity="fid:test",
        fields_to_update={"verdict": "false_positive"},
        update_reason="should fail",
    )

    assert result.success is False
    assert "参数校验失败" in str(result.error)
    assert "禁止更新字段" in str(result.data)


@pytest.mark.asyncio
async def test_report_agent_returns_updated_finding_after_update_tool():
    updated_findings: List[Dict[str, Any]] = []

    async def _update_callback(identity: str, patch: Dict[str, Any], reason: str) -> Dict[str, Any]:
        updated = {
            "finding_identity": identity,
            "file_path": "app/api.py",
            "line_start": 10,
            "line_end": 11,
            "function_name": "correct_func",
            "title": "app/api.py中correct_func函数SQL注入漏洞",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "verification_result": {
                "localization_status": "success",
                "verification_evidence": "report stage corrected line and function",
            },
        }
        if "verification_result" in patch:
            updated["verification_result"].update(patch["verification_result"])
        updated.update({k: v for k, v in patch.items() if k != "verification_result"})
        updated_findings.append(updated)
        return updated

    llm = _SequenceLLM(
        [
            (
                "Thought: 先读取源码并修正错误定位。\n"
                "Action: read_file\n"
                'Action Input: {"file_path": "app/api.py", "start_line": 1, "end_line": 20}'
            ),
            (
                "Thought: 已确认原始行号和函数名错误，先修正 finding。\n"
                "Action: update_vulnerability_finding\n"
                'Action Input: {"finding_identity": "fid:test", "fields_to_update": {"line_start": 10, "line_end": 11, "function_name": "correct_func", "title": "app/api.py中correct_func函数SQL注入漏洞", "verification_result.localization_status": "success", "verification_result.verification_evidence": "report stage corrected line and function"}, "update_reason": "Report阶段核对源码后修正定位"}'
            ),
            (
                "Thought: 信息已充分，输出报告。\n"
                "Final Answer:\n"
                "# 漏洞报告：app/api.py中correct_func函数SQL注入漏洞\n\n"
                "## 漏洞概述\n\n已完成修正。"
            ),
        ]
    )
    tools = {
        "read_file": _ReadFileTool(),
        "update_vulnerability_finding": UpdateVulnerabilityFindingTool(
            task_id="task-3",
            update_callback=_update_callback,
        ),
    }
    agent = ReportAgent(llm_service=llm, tools=tools, event_emitter=None)

    result = await agent.run(
        {
            "finding": {
                "finding_identity": "fid:test",
                "title": "wrong title",
                "file_path": "app/api.py",
                "line_start": 99,
                "vulnerability_type": "sql_injection",
                "severity": "high",
                "verdict": "confirmed",
                "confidence": 0.9,
                "function_name": "wrong_func",
            },
            "project_info": {"name": "demo"},
            "config": {},
        }
    )

    assert result.success is True
    assert updated_findings
    assert result.data["updated_finding"]["line_start"] == 10
    assert result.data["finding_validated"] is True
    assert "correct_func" in result.data["vulnerability_report"]


@pytest.mark.asyncio
async def test_report_agent_rejects_inconsistent_final_finding_identity():
    async def _update_callback(identity: str, patch: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "finding_identity": "fid:other",
            "title": "app/api.py中correct_func函数SQL注入漏洞",
            "file_path": "app/api.py",
            "line_start": 10,
            "line_end": 11,
            "function_name": "correct_func",
            "vulnerability_type": "sql_injection",
            "severity": "high",
        }

    llm = _SequenceLLM(
        [
            (
                "Thought: 先读取源码。\n"
                "Action: read_file\n"
                'Action Input: {"file_path": "app/api.py", "start_line": 1, "end_line": 20}'
            ),
            (
                "Thought: 需要修正 finding。\n"
                "Action: update_vulnerability_finding\n"
                'Action Input: {"finding_identity": "fid:test", "fields_to_update": {"line_start": 10, "line_end": 11, "function_name": "correct_func"}, "update_reason": "Report阶段核对源码后修正定位"}'
            ),
            (
                "Thought: 信息已充分，输出报告。\n"
                "Final Answer:\n"
                "# 漏洞报告：app/api.py中correct_func函数SQL注入漏洞\n\n"
                "## 漏洞概述\n\n已完成修正。"
            ),
        ]
    )
    agent = ReportAgent(
        llm_service=llm,
        tools={
            "read_file": _ReadFileTool(),
            "update_vulnerability_finding": UpdateVulnerabilityFindingTool(
                task_id="task-4",
                update_callback=_update_callback,
            ),
        },
        event_emitter=None,
    )

    result = await agent.run(
        {
            "finding": {
                "finding_identity": "fid:test",
                "title": "wrong title",
                "file_path": "app/api.py",
                "line_start": 99,
                "vulnerability_type": "sql_injection",
                "severity": "high",
                "verdict": "confirmed",
                "confidence": 0.9,
                "function_name": "wrong_func",
            },
            "project_info": {"name": "demo"},
            "config": {},
        }
    )

    assert result.success is False
    assert "finding_identity" in str(result.error)
    assert result.data["finding_validated"] is False


@pytest.mark.asyncio
async def test_save_findings_second_pass_persists_report_updates(db, test_agent_task, tmp_path: Path):
    project_root = tmp_path
    source_file = project_root / "app" / "api.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "def correct_func(user_input):\n"
        "    sink(user_input)\n",
        encoding="utf-8",
    )

    finding = {
        "finding_identity": "fid:report-sync",
        "title": "app/api.py中correct_func函数SQL注入漏洞",
        "file_path": "app/api.py",
        "line_start": 2,
        "line_end": 2,
        "function_name": "correct_func",
        "vulnerability_type": "sql_injection",
        "severity": "high",
        "description": "initial description",
        "verdict": "confirmed",
        "confidence": 0.95,
        "reachability": "reachable",
        "verification_evidence": "verified from source to sink",
        "verification_result": {
            "authenticity": "confirmed",
            "verdict": "confirmed",
            "confidence": 0.95,
            "reachability": "reachable",
            "verification_evidence": "verified from source to sink",
        },
    }

    saved_count = await _save_findings(
        db,
        test_agent_task.id,
        [dict(finding)],
        project_root=str(project_root),
    )
    assert saved_count == 1

    updated = dict(finding)
    updated["description"] = "report corrected description"
    updated["vulnerability_report"] = "# final markdown report"

    synced_count = await _save_findings(
        db,
        test_agent_task.id,
        [updated],
        project_root=str(project_root),
    )
    assert synced_count == 1

    result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id == test_agent_task.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    persisted = rows[0]
    assert persisted.report == "# final markdown report"
    assert persisted.description == "report corrected description"
