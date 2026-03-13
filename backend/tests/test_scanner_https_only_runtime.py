import builtins
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
async def test_scan_repo_task_does_not_import_legacy_ssh_module_for_https_repo(monkeypatch):
    task = SimpleNamespace(
        id="task-https",
        project_id="project-https",
        status="pending",
        started_at=None,
        branch_name="main",
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
        repository_url="https://github.com/org/repo.git",
        repository_type="github",
        default_branch="main",
    )
    tracked_module_name = ".".join(["app", "services", "_".join(["git", "ssh", "service"])])
    imported_legacy_ssh_module = {"value": False}
    original_import = builtins.__import__

    def _tracked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == tracked_module_name:
            imported_legacy_ssh_module["value"] = True
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(scanner_module, "LLMService", _FakeLLMService)
    monkeypatch.setattr(scanner_module, "get_github_files", AsyncMock(return_value=[]))
    monkeypatch.setattr(builtins, "__import__", _tracked_import)

    await scanner_module.scan_repo_task(
        "task-https",
        lambda: _FakeScannerSession(task, project),
        user_config={"otherConfig": {}},
    )

    assert imported_legacy_ssh_module["value"] is False
