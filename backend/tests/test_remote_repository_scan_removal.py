from types import SimpleNamespace
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

fastmcp_stub = types.ModuleType("fastmcp")
fastmcp_stub.Client = object
fastmcp_stub.FastMCP = object
fastmcp_client_stub = types.ModuleType("fastmcp.client")
fastmcp_transports_stub = types.ModuleType("fastmcp.client.transports")
fastmcp_transports_stub.StdioTransport = object
fastmcp_transports_stub.StreamableHttpTransport = object
git_stub = types.ModuleType("git")
git_stub.Repo = object
weasyprint_stub = types.ModuleType("weasyprint")
weasyprint_stub.HTML = object
weasyprint_stub.CSS = object
weasyprint_text_stub = types.ModuleType("weasyprint.text")
weasyprint_fonts_stub = types.ModuleType("weasyprint.text.fonts")
weasyprint_fonts_stub.FontConfiguration = object
sys.modules.setdefault("fastmcp", fastmcp_stub)
sys.modules.setdefault("fastmcp.client", fastmcp_client_stub)
sys.modules.setdefault("fastmcp.client.transports", fastmcp_transports_stub)
sys.modules.setdefault("git", git_stub)
sys.modules.setdefault("weasyprint", weasyprint_stub)
sys.modules.setdefault("weasyprint.text", weasyprint_text_stub)
sys.modules.setdefault("weasyprint.text.fonts", weasyprint_fonts_stub)

from app.api.v1.endpoints.agent_tasks import AgentTaskCreate, create_agent_task
from app.api.v1.endpoints.config import get_default_config
from app.api.v1.endpoints import projects as projects_module
from app.services.report_generator import ReportGenerator


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


def test_projects_router_no_longer_exposes_legacy_scan_route():
    route_paths = {route.path for route in projects_module.router.routes}

    assert "/{id}/scan" not in route_paths
    assert hasattr(projects_module, "scan_project") is False


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
