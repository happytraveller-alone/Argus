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
async def test_create_agent_task_generate_poc_without_authorization_is_normalized():
    db = _mock_db_with_project()
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=False,
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
    assert isinstance(task.agent_config, dict)
    assert task.agent_config.get("authorization_confirmed") is False


@pytest.mark.asyncio
async def test_create_agent_task_generate_poc_without_target_files_is_normalized():
    db = _mock_db_with_project()
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=False,
        target_files=[],
    )

    task = await create_agent_task(
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files is None
    assert isinstance(task.agent_config, dict)
    assert task.agent_config.get("authorization_confirmed") is False


@pytest.mark.asyncio
async def test_create_agent_task_generate_poc_with_authorization_and_targets_succeeds():
    db = _mock_db_with_project()
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=True,
        target_files=["src/app.py", "src/api.py"],
    )

    task = await create_agent_task(
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files == ["src/app.py", "src/api.py"]
    assert isinstance(task.agent_config, dict)
    assert task.agent_config.get("authorization_confirmed") is True
    db.commit.assert_awaited()
