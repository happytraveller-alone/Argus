from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.static_tasks import (
    get_static_task_finding_context,
    get_static_task_finding,
)


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_static_task_finding_returns_404_when_task_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(None),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_static_task_finding(
            task_id="missing-task",
            finding_id="finding-1",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "任务不存在"


@pytest.mark.asyncio
async def test_get_static_task_finding_returns_404_when_finding_not_found_or_not_owned():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1")),
            _ScalarOneOrNoneResult(None),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_static_task_finding(
            task_id="task-1",
            finding_id="missing-finding",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "漏洞不存在"


@pytest.mark.asyncio
async def test_get_static_task_finding_returns_enriched_finding_payload():
    finding = SimpleNamespace(
        id="finding-1",
        scan_task_id="task-1",
        rule={
            "check_id": "python.security.sql-injection",
            "extra": {
                "message": "Possible SQL injection",
                "metadata": {"references": ["https://example.com/rule"]},
            },
        },
        description="Possible SQL injection",
        file_path="src/app/db.py",
        start_line=23,
        code_snippet="query = f\"SELECT * FROM users WHERE id = {user_id}\"",
        severity="ERROR",
        status="open",
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(SimpleNamespace(id="task-1", project_id="project-1")),
            _ScalarOneOrNoneResult(finding),
            _AllResult(
                [
                    (
                        "python.security.sql-injection",
                        "HIGH",
                        ["CWE-89"],
                    )
                ]
            ),
        ]
    )

    result = await get_static_task_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["id"] == "finding-1"
    assert result["scan_task_id"] == "task-1"
    assert result["confidence"] == "HIGH"
    assert result["cwe"] == ["CWE-89"]
    assert result["rule_name"] == "python.security.sql-injection"
    assert result["resolved_file_path"] == "src/app/db.py"
    assert result["resolved_line_start"] == 23


@pytest.mark.asyncio
async def test_get_static_task_finding_context_accepts_paths_with_zip_root_prefix(
    monkeypatch,
    tmp_path,
):
    project_root = tmp_path / "openclaw-2026.3.7"
    source_file = project_root / "src" / "discord" / "voice-message.ts"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "const noop = 0;"
                if index == 1
                else "const url = input;"
                if index == 264
                else "const res = await fetch(url, {});"
                if index == 265
                else "const method = \"POST\";"
                if index == 266
                else f"line {index}"
                for index in range(1, 271)
            ]
        ),
        encoding="utf-8",
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(
                SimpleNamespace(id="task-1", project_id="project-1"),
            ),
            _ScalarOneOrNoneResult(
                SimpleNamespace(
                    id="finding-1",
                    scan_task_id="task-1",
                    file_path="openclaw-2026.3.7/src/discord/voice-message.ts",
                    start_line=265,
                    rule={},
                )
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.static_tasks_opengrep._get_project_root",
        AsyncMock(return_value=str(project_root)),
    )

    result = await get_static_task_finding_context(
        task_id="task-1",
        finding_id="finding-1",
        before=1,
        after=1,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["file_path"] == "src/discord/voice-message.ts"
    assert result["start_line"] == 265
    assert result["end_line"] == 265
    assert [line["line_number"] for line in result["lines"]] == [264, 265, 266]

