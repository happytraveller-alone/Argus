from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints.agent_tasks import AgentTaskCreate, create_agent_task
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


def _mock_db_with_project(project_id: str = "project-1"):
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(id=project_id, name="demo-project", source_type="zip")
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verification_level",
    [
        "analysis_only",
        "sandbox",
        "generate_poc",
        "poc_plan",
        "analysis_with_poc_plan",
        "unexpected_value",
        None,
    ],
)
async def test_create_agent_task_normalizes_verification_level(verification_level):
    db = _mock_db_with_project()
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level=verification_level,  # type: ignore[arg-type]
        target_files=["src/app.py"],
    )

    task = await create_agent_task(
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files == ["src/app.py"]
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_agent_task_merges_system_core_exclude_patterns():
    db = _mock_db_with_project()
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="analysis_with_poc_plan",
        exclude_patterns=["custom/**", "test/**"],
    )

    task = await create_agent_task(
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert "custom/**" in (task.exclude_patterns or [])
    assert "test/**" in (task.exclude_patterns or [])
    assert "**/.*/**" in (task.exclude_patterns or [])
    assert "**/*.yaml" in (task.exclude_patterns or [])
