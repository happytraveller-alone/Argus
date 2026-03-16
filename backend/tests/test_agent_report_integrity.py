from datetime import datetime, timezone
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
async def test_generate_report_keeps_long_text_and_escapes_markdown_fields():
    task_id = "task-1"
    long_description = "这是一段很长的漏洞描述。" * 600
    long_path = "src/security/[core](module)#file.py"
    title_with_markdown = "Unsafe [link](x) #1 | critical"

    finding = SimpleNamespace(
        id="finding-1",
        severity="high",
        title=title_with_markdown,
        vulnerability_type="xss",
        description=long_description,
        file_path=long_path,
        line_start=12,
        line_end=15,
        code_snippet=None,
        is_verified=False,
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        ai_confidence=0.92,
        suggestion=None,
        fix_code=None,
        created_at=datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc),
    )

    task = SimpleNamespace(
        id=task_id,
        project_id="project-1",
        status="completed",
        completed_at=datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc),
        security_score=75,
        analyzed_files=10,
        total_files=10,
        total_iterations=20,
        tool_calls_count=30,
        tokens_used=2048,
    )
    project = SimpleNamespace(id="project-1", name="Demo [Project] #1")

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id=task_id,
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert response.media_type == "text/markdown; charset=utf-8"

    assert "Unsafe \\[link\\]\\(x\\) \\#1 \\| critical" in body
    assert "src/security/\\[core\\]\\(module\\)\\#file.py:12-15" in body
    assert long_description in body
    assert "VulHunter" not in body
    assert "VulHunter" not in body
