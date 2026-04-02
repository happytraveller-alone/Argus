from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.agent_tasks_routes_results import update_finding_status
from app.models.agent_task import AgentFinding, AgentTask, FindingStatus, VulnerabilitySeverity
from app.models.project import Project


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_update_finding_status_marks_finding_verified_and_recomputes_task_counters():
    task = SimpleNamespace(
        id="task-1",
        project_id="project-1",
        findings_count=0,
        verified_count=0,
        false_positive_count=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
    )
    finding = AgentFinding(
        id="finding-1",
        task_id=task.id,
        vulnerability_type="xss",
        severity=VulnerabilitySeverity.HIGH,
        title="pending finding",
        description="waiting for manual review",
        status=FindingStatus.NEEDS_REVIEW,
        is_verified=False,
        verdict="likely",
        verification_result={
            "status": FindingStatus.NEEDS_REVIEW,
            "authenticity": "likely",
            "verdict": "likely",
            "verification_stage_completed": True,
        },
    )

    db = AsyncMock()

    async def get_side_effect(model, object_id):
        if model is AgentTask and object_id == task.id:
            return task
        if model is Project and object_id == task.project_id:
            return SimpleNamespace(id=task.project_id)
        if model is AgentFinding and object_id == finding.id:
            return finding
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))
    db.commit = AsyncMock()

    result = await update_finding_status(
        task_id=task.id,
        finding_id=finding.id,
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["status"] == FindingStatus.VERIFIED
    assert finding.status == FindingStatus.VERIFIED
    assert finding.is_verified is True
    assert finding.verified_at is not None
    assert finding.verdict == "confirmed"
    assert finding.verification_result["status"] == FindingStatus.VERIFIED
    assert finding.verification_result["authenticity"] == "confirmed"
    assert finding.verification_result["verdict"] == "confirmed"
    assert task.findings_count == 1
    assert task.verified_count == 1
    assert task.false_positive_count == 0
    assert task.high_count == 1


@pytest.mark.asyncio
async def test_update_finding_status_marks_finding_false_positive_and_hides_it_from_task_counts():
    task = SimpleNamespace(
        id="task-1",
        project_id="project-1",
        findings_count=0,
        verified_count=0,
        false_positive_count=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
    )
    finding = AgentFinding(
        id="finding-1",
        task_id=task.id,
        vulnerability_type="sql_injection",
        severity=VulnerabilitySeverity.MEDIUM,
        title="likely finding",
        description="waiting for manual review",
        status=FindingStatus.NEEDS_REVIEW,
        is_verified=False,
        verdict="confirmed",
        verification_result={
            "status": FindingStatus.NEEDS_REVIEW,
            "authenticity": "confirmed",
            "verdict": "confirmed",
            "verification_stage_completed": True,
        },
    )

    db = AsyncMock()

    async def get_side_effect(model, object_id):
        if model is AgentTask and object_id == task.id:
            return task
        if model is Project and object_id == task.project_id:
            return SimpleNamespace(id=task.project_id)
        if model is AgentFinding and object_id == finding.id:
            return finding
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))
    db.commit = AsyncMock()

    result = await update_finding_status(
        task_id=task.id,
        finding_id=finding.id,
        status="false_positive",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["status"] == FindingStatus.FALSE_POSITIVE
    assert finding.status == FindingStatus.FALSE_POSITIVE
    assert finding.is_verified is False
    assert finding.verified_at is None
    assert finding.verdict == "false_positive"
    assert finding.verification_result["status"] == FindingStatus.FALSE_POSITIVE
    assert finding.verification_result["authenticity"] == "false_positive"
    assert finding.verification_result["verdict"] == "false_positive"
    assert task.findings_count == 0
    assert task.verified_count == 0
    assert task.false_positive_count == 1
    assert task.medium_count == 0
