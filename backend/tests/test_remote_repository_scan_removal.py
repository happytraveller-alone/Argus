from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.v1.endpoints.agent_tasks import AgentTaskCreate, create_agent_task
from app.api.v1.endpoints.config import get_default_config
from app.api.v1.endpoints.projects import ScanRequest, scan_project
from app.services.report_generator import ReportGenerator


class _ExecuteResult:
    def scalar_one_or_none(self):
        return None


@pytest.mark.asyncio
async def test_create_agent_task_rejects_repository_project():
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(
            id="project-1",
            name="repo-project",
            source_type="repository",
            repository_url="https://github.com/example/repo.git",
        )
    )
    db.add = MagicMock()

    with pytest.raises(HTTPException, match="仅支持 ZIP 项目"):
        await create_agent_task(
            request=AgentTaskCreate(project_id="project-1"),
            background_tasks=BackgroundTasks(),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_scan_project_does_not_store_branch_name_for_zip_projects():
    project = SimpleNamespace(id="project-1", source_type="zip")
    db = AsyncMock()
    db.get = AsyncMock(return_value=project)
    db.execute = AsyncMock(return_value=_ExecuteResult())
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    response = await scan_project(
        id="project-1",
        background_tasks=BackgroundTasks(),
        scan_request=ScanRequest(file_paths=["src/app.py"], exclude_patterns=["node_modules"]),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    created_task = db.add.call_args.args[0]
    assert response["status"] == "started"
    assert created_task.branch_name is None


def test_get_default_config_omits_git_tokens():
    config = get_default_config()

    assert "githubToken" not in config["otherConfig"]
    assert "gitlabToken" not in config["otherConfig"]


def test_generate_task_report_omits_branch_from_subtitle(monkeypatch):
    captured = {}

    def _fake_render_pdf(context):
        captured["context"] = context
        return b"pdf"

    monkeypatch.setattr(ReportGenerator, "_render_pdf", classmethod(lambda cls, context: _fake_render_pdf(context)))

    result = ReportGenerator.generate_task_report(
        {
            "id": "task-1",
            "quality_score": 80,
            "scanned_files": 2,
            "total_lines": 20,
            "branch_name": "legacy-branch",
        },
        [],
        "demo-project",
    )

    assert result == b"pdf"
    assert captured["context"]["subtitle"] == "项目: demo-project"
