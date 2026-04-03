from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys
import types

import pytest

if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.errors = types.SimpleNamespace(
        DockerException=Exception,
        NotFound=Exception,
    )
    docker_stub.from_env = lambda: None
    sys.modules["docker"] = docker_stub

from app.api.v1.endpoints.agent_tasks_reporting import generate_audit_report
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


@pytest.mark.asyncio
async def test_update_finding_status_is_reflected_in_followup_report_export_json_summary():
    task = SimpleNamespace(
        id="task-1",
        project_id="project-1",
        status="completed",
        security_score=75,
        analyzed_files=10,
        total_files=10,
        findings_count=0,
        verified_count=0,
        false_positive_count=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        total_iterations=20,
        tool_calls_count=30,
        tokens_used=2048,
        started_at=None,
        completed_at=None,
        report="项目报告正文",
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
        verdict="likely",
        verification_result={
            "status": FindingStatus.NEEDS_REVIEW,
            "authenticity": "likely",
            "verdict": "likely",
            "verification_stage_completed": True,
        },
    )

    update_db = AsyncMock()

    async def update_get_side_effect(model, object_id):
        if model is AgentTask and object_id == task.id:
            return task
        if model is Project and object_id == task.project_id:
            return SimpleNamespace(id=task.project_id, name="Demo")
        if model is AgentFinding and object_id == finding.id:
            return finding
        return None

    update_db.get = AsyncMock(side_effect=update_get_side_effect)
    update_db.execute = AsyncMock(return_value=_ScalarListResult([finding]))
    update_db.commit = AsyncMock()

    result = await update_finding_status(
        task_id=task.id,
        finding_id=finding.id,
        status="false_positive",
        db=update_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["status"] == FindingStatus.FALSE_POSITIVE
    assert task.findings_count == 0
    assert task.false_positive_count == 1

    report_db = AsyncMock()
    report_db.get = AsyncMock(
        side_effect=[
            task,
            SimpleNamespace(id=task.project_id, name="Demo"),
        ]
    )
    report_db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    payload = await generate_audit_report(
        task_id=task.id,
        format="json",
        db=report_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert payload["summary"]["status_distribution"] == {
        "pending": 0,
        "verified": 0,
        "false_positive": 1,
    }
    assert payload["summary"]["false_positive_findings"] == 1
