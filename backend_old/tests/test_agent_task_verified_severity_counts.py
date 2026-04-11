from datetime import datetime, timezone
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.errors = types.SimpleNamespace(
        DockerException=Exception,
        NotFound=Exception,
    )
    docker_stub.from_env = lambda: None
    sys.modules["docker"] = docker_stub

from app.api.v1.endpoints.agent_tasks_routes_tasks import (
    _load_defect_summaries,
    get_agent_task,
    list_agent_tasks,
)
from app.models.agent_task import AgentTask, AgentTaskStatus
from app.models.project import Project


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FetchAllResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


@pytest.mark.asyncio
async def test_load_defect_summaries_formats_all_status_and_severity_buckets():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_FetchAllResult(
            [
                (
                    "task-1",
                    4,
                    1,
                    2,
                    1,
                    0,
                    0,
                    1,
                    2,
                    1,
                )
            ]
        )
    )

    result = await _load_defect_summaries(db, ["task-1"])

    assert result == {
        "task-1": {
            "scope": "all_findings",
            "total_count": 4,
            "severity_counts": {
                "critical": 1,
                "high": 2,
                "medium": 1,
                "low": 0,
                "info": 0,
            },
            "status_counts": {
                "pending": 1,
                "verified": 2,
                "false_positive": 1,
            },
        }
    }


@pytest.mark.asyncio
async def test_list_agent_tasks_returns_verified_severity_buckets_and_defect_summary(
    monkeypatch,
):
    task = AgentTask(
        id="task-1",
        project_id="project-1",
        created_by="user-1",
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

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _FetchAllResult([("project-1",)]),
            _ScalarListResult([task]),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_routes_tasks._load_verified_severity_counts",
        AsyncMock(return_value={"task-1": {"critical": 1, "high": 0, "medium": 1, "low": 0}}),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_routes_tasks._load_defect_summaries",
        AsyncMock(
            return_value={
                "task-1": {
                    "scope": "all_findings",
                    "total_count": 4,
                    "severity_counts": {
                        "critical": 1,
                        "high": 2,
                        "medium": 1,
                        "low": 0,
                        "info": 0,
                    },
                    "status_counts": {
                        "pending": 1,
                        "verified": 2,
                        "false_positive": 1,
                    },
                }
            }
        ),
    )

    tasks = await list_agent_tasks(
        db=db,
        current_user=SimpleNamespace(id="user-1"),
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
    assert item.defect_summary.model_dump() == {
        "scope": "all_findings",
        "total_count": 4,
        "severity_counts": {
            "critical": 1,
            "high": 2,
            "medium": 1,
            "low": 0,
            "info": 0,
        },
        "status_counts": {
            "pending": 1,
            "verified": 2,
            "false_positive": 1,
        },
    }


@pytest.mark.asyncio
async def test_get_agent_task_returns_defect_summary(monkeypatch):
    task = SimpleNamespace(
        id="task-detail",
        project_id="project-1",
        name="智能扫描-Detail",
        description="[INTELLIGENT]智能扫描任务",
        task_type="agent_audit",
        status="completed",
        current_phase="reporting",
        current_step=None,
        total_files=0,
        indexed_files=0,
        analyzed_files=0,
        total_chunks=0,
        total_iterations=1,
        tool_calls_count=1,
        tokens_used=10,
        findings_count=2,
        verified_count=1,
        false_positive_count=0,
        critical_count=1,
        high_count=0,
        medium_count=1,
        low_count=0,
        quality_score=0.0,
        security_score=0.0,
        progress_percentage=100.0,
        created_at=datetime(2026, 2, 12, 8, 0, 0, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        error_message=None,
        audit_scope=None,
        target_vulnerabilities=None,
        verification_level="analysis_with_poc_plan",
        exclude_patterns=None,
        target_files=None,
        report=None,
        agent_config={"tool_evidence_protocol": "native_v1"},
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return task
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_routes_tasks._load_verified_severity_counts",
        AsyncMock(return_value={"task-detail": {"critical": 1, "high": 0, "medium": 0, "low": 0}}),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_routes_tasks._load_defect_summaries",
        AsyncMock(
            return_value={
                "task-detail": {
                    "scope": "all_findings",
                    "total_count": 2,
                    "severity_counts": {
                        "critical": 1,
                        "high": 0,
                        "medium": 1,
                        "low": 0,
                        "info": 0,
                    },
                    "status_counts": {
                        "pending": 1,
                        "verified": 1,
                        "false_positive": 0,
                    },
                }
            }
        ),
    )

    item = await get_agent_task(
        task_id="task-detail",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert item.tool_evidence_protocol == "native_v1"
    assert item.defect_summary.model_dump() == {
        "scope": "all_findings",
        "total_count": 2,
        "severity_counts": {
            "critical": 1,
            "high": 0,
            "medium": 1,
            "low": 0,
            "info": 0,
        },
        "status_counts": {
            "pending": 1,
            "verified": 1,
            "false_positive": 0,
        },
    }
