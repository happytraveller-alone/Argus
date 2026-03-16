from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import scanner as scanner_module


class _FakeLLMService:
    def __init__(self, user_config=None):
        self.user_config = user_config


class _FakeScannerSession:
    def __init__(self, task, project):
        self.task = task
        self.project = project

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, _id):
        if model is scanner_module.AuditTask:
            return self.task
        if model is scanner_module.Project:
            return self.project
        return None

    async def commit(self):
        return None

    def add(self, _value):
        return None


@pytest.mark.asyncio
async def test_scan_repo_task_rejects_non_zip_project(monkeypatch):
    task = SimpleNamespace(
        id="task-https",
        project_id="project-https",
        status="pending",
        started_at=None,
        exclude_patterns=None,
        total_files=0,
        scanned_files=0,
        total_lines=0,
        issues_count=0,
        quality_score=0,
        completed_at=None,
    )
    project = SimpleNamespace(
        id="project-https",
        source_type="repository",
        default_branch="main",
    )

    monkeypatch.setattr(scanner_module, "LLMService", _FakeLLMService)

    await scanner_module.scan_repo_task(
        "task-https",
        lambda: _FakeScannerSession(task, project),
        user_config={"otherConfig": {}},
    )

    assert task.status == "failed"
