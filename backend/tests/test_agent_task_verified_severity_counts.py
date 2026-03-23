from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.agent_tasks_routes_tasks import list_agent_tasks
from app.models.agent_task import AgentFinding, AgentTask, AgentTaskStatus


@pytest.mark.asyncio
async def test_list_agent_tasks_returns_verified_severity_buckets(
    db,
    test_project,
    test_user,
):
    task = AgentTask(
        project_id=test_project.id,
        created_by=test_user.id,
        name="智能扫描-Demo",
        description="[INTELLIGENT]智能扫描任务",
        task_type="agent_audit",
        status=AgentTaskStatus.COMPLETED,
        findings_count=4,
        verified_count=2,
        critical_count=1,
        high_count=2,
        medium_count=1,
        low_count=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(task)
    await db.flush()

    db.add_all(
        [
            AgentFinding(
                task_id=task.id,
                vulnerability_type="SQL Injection",
                severity="critical",
                title="Verified Critical",
                status="verified",
                is_verified=True,
                verdict="confirmed",
            ),
            AgentFinding(
                task_id=task.id,
                vulnerability_type="Auth Bypass",
                severity="medium",
                title="Verified Medium",
                status="verified",
                is_verified=True,
                verdict="likely",
            ),
            AgentFinding(
                task_id=task.id,
                vulnerability_type="XSS",
                severity="high",
                title="Pending High",
                status="new",
                is_verified=False,
                verdict="uncertain",
            ),
            AgentFinding(
                task_id=task.id,
                vulnerability_type="Hardcoded Secret",
                severity="high",
                title="False Positive High",
                status="false_positive",
                is_verified=False,
                verdict="false_positive",
            ),
        ]
    )
    await db.commit()

    tasks = await list_agent_tasks(
        db=db,
        current_user=SimpleNamespace(id=test_user.id),
        skip=0,
        limit=20,
    )

    assert len(tasks) == 1
    item = tasks[0]
    assert item.verified_count == 2
    assert item.verified_critical_count == 1
    assert item.verified_high_count == 0
    assert item.verified_medium_count == 1
    assert item.verified_low_count == 0
