from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import AgentTaskCreate, create_agent_task
from app.api.v1.endpoints import agent_tasks_routes_tasks
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


def _mock_db_with_project(project_id: str = "project-1"):
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(id=project_id, name="demo-project", source_type="zip")
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.in_transaction = MagicMock(return_value=False)
    return db


def _stub_background_launch(monkeypatch):
    created_tasks = []

    class _CreatedTask:
        def __init__(self, coro):
            self._coro = coro

        def cancel(self):
            self._coro.close()

    monkeypatch.setattr(
        agent_tasks_routes_tasks.asyncio,
        "create_task",
        lambda coro, name=None: created_tasks.append((name, coro)) or _CreatedTask(coro),
    )
    monkeypatch.setattr(
        agent_tasks_routes_tasks.project_metrics_refresher,
        "enqueue",
        lambda *_args, **_kwargs: None,
    )
    return created_tasks


@pytest.mark.asyncio
async def test_create_agent_task_generate_poc_without_authorization_is_normalized(monkeypatch):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=False,
        target_files=["src/app.py"],
    )

    task = await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files == ["src/app.py"]
    assert created_tasks

    for _name, coro in created_tasks:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_generate_poc_without_target_files_is_normalized(monkeypatch):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=False,
        target_files=[],
    )

    task = await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files is None
    assert created_tasks

    for _name, coro in created_tasks:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_generate_poc_with_authorization_and_targets_succeeds(monkeypatch):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="generate_poc",
        authorization_confirmed=True,
        target_files=["src/app.py", "src/api.py"],
    )

    task = await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files == ["src/app.py", "src/api.py"]
    db.commit.assert_awaited()
    assert created_tasks

    for _name, coro in created_tasks:
        coro.close()
