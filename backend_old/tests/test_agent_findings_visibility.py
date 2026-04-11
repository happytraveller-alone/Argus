from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.agent_tasks_routes_results import list_agent_findings
from app.models.agent_task import AgentTask
from app.models.project import Project
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_list_agent_findings_hides_false_positive_by_default():
    task_id = "task-1"
    now = datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc)

    finding_confirmed = SimpleNamespace(
        id="finding-1",
        task_id=task_id,
        vulnerability_type="xss",
        severity="high",
        title="confirmed issue",
        description="confirmed",
        file_path="/tmp/audit-workspace/app.py",
        line_start=10,
        line_end=11,
        code_snippet="dangerous()",
        code_context="line9\nline10\nline11",
        is_verified=True,
        ai_confidence=0.92,
        status="verified",
        suggestion="fix",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={
            "authenticity": "confirmed",
            "reachability": "reachable",
            "evidence": "verified by harness",
            "context_start_line": 8,
            "context_end_line": 13,
            "reachability_target": {
                "file_path": "/tmp/audit-workspace/app.py",
                "function": "dangerous",
                "start_line": 7,
                "end_line": 18,
            },
        },
        created_at=now,
    )
    finding_false_positive = SimpleNamespace(
        id="finding-2",
        task_id=task_id,
        vulnerability_type="xss",
        severity="low",
        title="false positive issue",
        description="false positive",
        file_path="/tmp/audit-workspace/app.py",
        line_start=20,
        line_end=20,
        code_snippet="safe()",
        code_context="line19\nline20\nline21",
        is_verified=False,
        ai_confidence=0.1,
        status="false_positive",
        suggestion=None,
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={
            "authenticity": "false_positive",
            "reachability": "unreachable",
            "evidence": "cannot reproduce",
            "context_start_line": 18,
            "context_end_line": 22,
            "verification_todo_id": "todo-fp-1",
            "verification_fingerprint": "fp-fp-1",
        },
        finding_metadata={
            "verification_todo_id": "todo-fp-1",
            "verification_fingerprint": "fp-fp-1",
        },
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([finding_confirmed, finding_false_positive]))

    only_effective = await list_agent_findings(
        task_id=task_id,
        include_false_positive=False,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert len(only_effective) == 1
    assert only_effective[0].id == "finding-1"
    assert only_effective[0].file_path == "app.py"
    assert only_effective[0].resolved_file_path == "app.py"
    assert only_effective[0].resolved_line_start == 10
    assert only_effective[0].reachability_file == "app.py"
    assert "该漏洞位于app.py:10-11的dangerous函数中" in (only_effective[0].description or "")
    assert "程序在该路径上缺少必要的输入约束或边界校验处理" in (only_effective[0].description or "")
    assert "漏洞详情：" not in (only_effective[0].description or "")
    assert only_effective[0].cwe_id == "CWE-79"
    assert only_effective[0].function_trigger_flow
    assert only_effective[0].reachability_function_start_line == 7
    assert only_effective[0].reachability_function_end_line == 18

    all_findings = await list_agent_findings(
        task_id=task_id,
        include_false_positive=True,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert len(all_findings) == 2
    false_positive = next(item for item in all_findings if item.id == "finding-2")
    assert false_positive.authenticity == "false_positive"
    assert false_positive.verification_evidence == "cannot reproduce"
    assert false_positive.verification_todo_id == "todo-fp-1"
    assert false_positive.verification_fingerprint == "fp-fp-1"


@pytest.mark.asyncio
async def test_list_agent_findings_verified_only_excludes_pending_and_false_positive():
    task_id = "task-verified"
    now = datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc)

    verified_finding = SimpleNamespace(
        id="finding-verified",
        task_id=task_id,
        vulnerability_type="xss",
        severity="high",
        title="verified issue",
        description="verified",
        file_path="/tmp/audit-workspace/app.py",
        line_start=10,
        line_end=11,
        code_snippet="dangerous()",
        code_context="line9\nline10\nline11",
        is_verified=True,
        ai_confidence=0.92,
        status="verified",
        suggestion="fix",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "confirmed"},
        created_at=now,
    )
    pending_finding = SimpleNamespace(
        id="finding-pending",
        task_id=task_id,
        vulnerability_type="idor",
        severity="medium",
        title="pending issue",
        description="pending",
        file_path="/tmp/audit-workspace/app.py",
        line_start=20,
        line_end=20,
        code_snippet="pending()",
        code_context="line19\nline20\nline21",
        is_verified=False,
        ai_confidence=0.72,
        status="pending",
        suggestion=None,
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "likely"},
        created_at=now,
    )
    false_positive_finding = SimpleNamespace(
        id="finding-fp",
        task_id=task_id,
        vulnerability_type="xss",
        severity="low",
        title="false positive issue",
        description="false positive",
        file_path="/tmp/audit-workspace/app.py",
        line_start=30,
        line_end=30,
        code_snippet="safe()",
        code_context="line29\nline30\nline31",
        is_verified=False,
        ai_confidence=0.1,
        status="false_positive",
        suggestion=None,
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "false_positive"},
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(
        return_value=_ScalarListResult(
            [verified_finding, pending_finding, false_positive_finding]
        )
    )

    results = await list_agent_findings(
        task_id=task_id,
        verified_only=True,
        include_false_positive=False,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.id for item in results] == ["finding-verified"]


@pytest.mark.asyncio
async def test_list_agent_findings_verified_only_keeps_status_verified_items():
    task_id = "task-status-verified"
    now = datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc)

    likely_verified_finding = SimpleNamespace(
        id="finding-likely",
        task_id=task_id,
        vulnerability_type="ssrf",
        severity="medium",
        title="likely issue",
        description="likely",
        file_path="/tmp/audit-workspace/app.py",
        line_start=40,
        line_end=41,
        code_snippet="fetch_remote()",
        code_context="line39\nline40\nline41",
        is_verified=False,
        ai_confidence=0.61,
        status="verified",
        suggestion="fix",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "likely"},
        created_at=now,
    )
    pending_finding = SimpleNamespace(
        id="finding-pending",
        task_id=task_id,
        vulnerability_type="idor",
        severity="medium",
        title="pending issue",
        description="pending",
        file_path="/tmp/audit-workspace/app.py",
        line_start=20,
        line_end=20,
        code_snippet="pending()",
        code_context="line19\nline20\nline21",
        is_verified=False,
        ai_confidence=0.72,
        status="pending",
        suggestion=None,
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "likely"},
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(
        return_value=_ScalarListResult([likely_verified_finding, pending_finding])
    )

    results = await list_agent_findings(
        task_id=task_id,
        verified_only=True,
        include_false_positive=False,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.id for item in results] == ["finding-likely"]


@pytest.mark.asyncio
async def test_list_agent_findings_verified_only_excludes_status_likely_items():
    task_id = "task-status-likely"
    now = datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc)

    likely_finding = SimpleNamespace(
        id="finding-likely-status",
        task_id=task_id,
        vulnerability_type="memory_corruption",
        severity="high",
        title="likely status issue",
        description="likely",
        file_path="/tmp/audit-workspace/app.py",
        line_start=44,
        line_end=48,
        code_snippet="free(ptr);",
        code_context="line43\nline44\nline45",
        is_verified=False,
        ai_confidence=0.74,
        status="likely",
        suggestion="fix",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={"authenticity": "likely", "status": "likely"},
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([likely_finding]))

    results = await list_agent_findings(
        task_id=task_id,
        verified_only=True,
        include_false_positive=False,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert results == []
