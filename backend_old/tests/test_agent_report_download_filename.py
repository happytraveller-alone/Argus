from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.agent_tasks import generate_audit_report


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_generate_audit_report_uses_project_based_download_filename():
    task = SimpleNamespace(
        id="task-12345678",
        project_id="project-1",
        status="completed",
        completed_at=None,
        started_at=None,
        security_score=75,
        analyzed_files=0,
        total_files=0,
        total_iterations=0,
        tool_calls_count=0,
        tokens_used=0,
        report=None,
    )
    project = SimpleNamespace(id="project-1", name="Demo 项目")

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([]))

    response = await generate_audit_report(
        task_id="task-12345678",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    content_disposition = response.headers.get("content-disposition", "")
    assert 'filename="' in content_disposition
    assert "filename*=UTF-8''" in content_disposition
    assert (
        "filename*=UTF-8''%E6%BC%8F%E6%B4%9E%E6%8A%A5%E5%91%8A-Demo%20%E9%A1%B9%E7%9B%AE-"
        in content_disposition
    )
    assert content_disposition.endswith(".md")
