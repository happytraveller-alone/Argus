from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.static_tasks_bandit import get_bandit_finding
from app.api.v1.endpoints.static_tasks_gitleaks import get_gitleaks_finding
from app.api.v1.endpoints.static_tasks_phpstan import get_phpstan_finding
from app.api.v1.endpoints.static_tasks_pmd import get_pmd_finding


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_get_gitleaks_finding_returns_resolved_location_fields(monkeypatch, tmp_path):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1", project_id="project-1")),
            _ScalarOneOrNoneResult(
                SimpleNamespace(
                    id="finding-1",
                    scan_task_id="task-1",
                    rule_id="generic-api-key",
                    description="Potential API key leak",
                    file_path=str(tmp_path / "src" / "config.ts"),
                    start_line=8,
                    end_line=8,
                    secret="***",
                    match="API_KEY=abcd",
                    commit="abc123",
                    author="Dev",
                    email="dev@example.com",
                    date="2026-03-01T00:00:00Z",
                    fingerprint="fp-1",
                    status="open",
                )
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.static_tasks_gitleaks._get_project_root",
        AsyncMock(return_value=str(tmp_path)),
    )

    result = await get_gitleaks_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.resolved_file_path == "src/config.ts"
    assert result.resolved_line_start == 8


@pytest.mark.asyncio
async def test_get_bandit_finding_returns_resolved_location_fields(monkeypatch, tmp_path):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1", project_id="project-1")),
            _ScalarOneOrNoneResult(
                SimpleNamespace(
                    id="finding-1",
                    scan_task_id="task-1",
                    test_id="B602",
                    test_name="subprocess_popen_with_shell_equals_true",
                    issue_severity="HIGH",
                    issue_confidence="HIGH",
                    file_path=str(tmp_path / "app" / "tasks" / "run_cmd.py"),
                    line_number=41,
                    code_snippet="subprocess.Popen(command, shell=True)",
                    issue_text="shell=True may trigger command injection",
                    more_info="https://bandit.readthedocs.io/",
                    status="open",
                )
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.static_tasks_bandit._get_project_root",
        AsyncMock(return_value=str(tmp_path)),
    )

    result = await get_bandit_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.resolved_file_path == "app/tasks/run_cmd.py"
    assert result.resolved_line_start == 41


@pytest.mark.asyncio
async def test_get_phpstan_finding_returns_resolved_location_fields(monkeypatch, tmp_path):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1", project_id="project-1")),
            _ScalarOneOrNoneResult(
                SimpleNamespace(
                    id="finding-1",
                    scan_task_id="task-1",
                    file_path=str(tmp_path / "src" / "Service.php"),
                    line=17,
                    message="Potential null dereference",
                    identifier="phpstan.nullsafe",
                    tip=None,
                    status="open",
                )
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.static_tasks_phpstan._get_project_root",
        AsyncMock(return_value=str(tmp_path)),
    )

    result = await get_phpstan_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.resolved_file_path == "src/Service.php"
    assert result.resolved_line_start == 17


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

