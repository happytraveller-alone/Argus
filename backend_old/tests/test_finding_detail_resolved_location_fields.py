from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.static_tasks_pmd import get_pmd_finding


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_get_pmd_finding_returns_resolved_location_fields(monkeypatch, tmp_path):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1", project_id="project-1")),
            _ScalarOneOrNoneResult(
                SimpleNamespace(
                    id="finding-1",
                    scan_task_id="task-1",
                    file_path=str(tmp_path / "src" / "main" / "java" / "App.java"),
                    begin_line=12,
                    end_line=13,
                    rule="AvoidDuplicateLiterals",
                    ruleset="category/java/errorprone.xml",
                    priority=2,
                    message="Duplicate literals found",
                    status="open",
                )
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.static_tasks_pmd._get_project_root",
        AsyncMock(return_value=str(tmp_path)),
    )

    result = await get_pmd_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.resolved_file_path == "src/main/java/App.java"
    assert result.resolved_line_start == 12
