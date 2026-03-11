from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.agent_tasks import get_agent_finding
from app.models.agent_task import AgentTask
from app.models.project import Project


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _build_agent_finding(
    *,
    finding_id: str,
    task_id: str,
    status: str = "verified",
):
    now = datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
    verification_result = {
        "authenticity": "confirmed" if status != "false_positive" else "false_positive",
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
        "verification_todo_id": "todo-1",
        "verification_fingerprint": "fp-1",
    }
    return SimpleNamespace(
        id=finding_id,
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
        is_verified=(status == "verified"),
        ai_confidence=0.92,
        status=status,
        suggestion="fix",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result=verification_result,
        references=["https://cwe.mitre.org/data/definitions/79.html"],
        verification_evidence="verified by harness",
        finding_metadata={
            "verification_todo_id": "todo-1",
            "verification_fingerprint": "fp-1",
        },
        created_at=now,
    )


@pytest.mark.asyncio
async def test_get_agent_finding_returns_404_when_task_not_found():
    db = AsyncMock()

    async def get_side_effect(model, _id):
        return None

    db.get = AsyncMock(side_effect=get_side_effect)

    with pytest.raises(HTTPException) as exc_info:
        await get_agent_finding(
            task_id="missing-task",
            finding_id="finding-1",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "任务不存在"


@pytest.mark.asyncio
async def test_get_agent_finding_returns_404_when_finding_not_found():
    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id="task-1", project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))

    with pytest.raises(HTTPException) as exc_info:
        await get_agent_finding(
            task_id="task-1",
            finding_id="missing-finding",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "发现不存在"


@pytest.mark.asyncio
async def test_get_agent_finding_returns_enriched_payload():
    task_id = "task-1"
    finding = _build_agent_finding(finding_id="finding-1", task_id=task_id)

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    result = await get_agent_finding(
        task_id=task_id,
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.id == "finding-1"
    assert result.task_id == task_id
    assert result.file_path == "app.py"
    assert result.reachability_file == "app.py"
    assert result.display_title


@pytest.mark.asyncio
async def test_get_agent_finding_can_include_false_positive():
    task_id = "task-1"
    finding = _build_agent_finding(
        finding_id="finding-fp",
        task_id=task_id,
        status="false_positive",
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    result = await get_agent_finding(
        task_id=task_id,
        finding_id="finding-fp",
        include_false_positive=True,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.id == "finding-fp"
    assert result.authenticity == "false_positive"
    assert result.verification_todo_id == "todo-1"
    assert result.verification_fingerprint == "fp-1"
    assert result.verification_evidence == "verified by harness"
